"""Clase principal AldesBridge: gestiona la comunicación entre la Connect Box y Home Assistant.

Incluye:
- Escucha TLS en el puerto local para la Connect Box.
- Filtro antidesconexión (grace timer de 30s) para ignorar el reinicio de sesión cada 5 horas.
- Integración con FilterTracker para el cálculo de los días restantes del filtro.
- Envío de comandos JSON-RPC (incluido el modo Vacaciones 'W' con fechas concatenadas).
"""
import json
import logging
import os
import socket
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import __version__, mqtt
from .config import TELEMETRY_CACHE_PATH, BridgeConfig, detect_mqtt_broker, load_translations
from .discovery import publish_homeassistant_discovery
from .filters import FilterTracker
from .models import TELEMETRY_SENSORS
from .tls import server_context

_log = logging.getLogger("aldes-sc150")

# Pausa mínima (en segundos) entre dos comandos enviados a la Connect Box para no saturar la UART
COMMAND_MIN_INTERVAL = 2.0
# Tiempo de espera (en segundos) antes de verificar si la VMC ha aplicado el cambio de modo
COMMAND_VERIFY_TIMEOUT = 15.0

def extract_json_dict(raw_payload: bytes | str) -> Optional[dict[str, Any]]:
    """Extrae el diccionario JSON del payload MQTT enviado por la Connect Box."""
    if isinstance(raw_payload, bytes):
        raw_payload = raw_payload.decode("utf-8", errors="replace")
    if not isinstance(raw_payload, str):
        return None
    json_start = raw_payload.find("{")
    if json_start < 0:
        return None
    try:
        parsed = json.loads(raw_payload[json_start:])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


class AldesBridge:
    """Coordina el servidor TLS hacia la VMC y el cliente MQTT hacia Home Assistant."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.translations = load_translations(config.language)

        # Configuración de modos de la VMC: V, Y, X, W se exponen en el selector de Home Assistant,
        # mientras que Z (Programa de aire) se reconoce en el código pero no se muestra en el desplegable.
        mode_labels = self.translations.get("modes", {})
        self.exposed_modes: dict[str, str] = {
            "V": mode_labels.get("V", "Quotidiano"),
            "Y": mode_labels.get("Y", "Cucina"),
            "X": mode_labels.get("X", "Boost"),
            "W": mode_labels.get("W", "Vacanze"),
        }
        self.label_to_mode_code: dict[str, str] = {
            label.lower(): code for code, label in self.exposed_modes.items()
        }
        self.all_known_modes: dict[str, str] = {
            **self.exposed_modes,
            "Z": mode_labels.get("Z", "Programma aria"),
        }

        # Estado de conexión de la Connect Box y temporizador antidesconexión (para el ciclo de 5 horas)
        self.box_socket: Optional[socket.socket] = None
        self.box_lock = threading.Lock()
        self.box_connected: bool = False
        self.disconnect_timer: Optional[threading.Timer] = None
        self.product_id: str = "98D8636921CA_AIR"
        self.rpc_command_id: int = 1
        self.box_packet_id: int = 1
        
        # Cola de envío y verificación automática de ejecución de comandos
        self.send_lock = threading.Lock()
        self.last_command_sent_at: float = 0.0
        self.pending_mode_code: Optional[str] = None
        self.verify_timer: Optional[threading.Timer] = None

        # Estado de conexión hacia el broker Mosquitto de Home Assistant
        self.ha_socket: Optional[socket.socket] = None
        self.ha_lock = threading.Lock()
        self.ha_packet_id: int = 1

        # Caché de telemetría y rastreador inteligente para los filtros
        self.last_telemetry: dict[str, Any] = self._load_telemetry_cache()
        self.filter_tracker = FilterTracker(filter_months=config.filter_months)

    # -------------------------------------------------------------------------
    # Gestión de caché de telemetría en disco
    # -------------------------------------------------------------------------

    def _load_telemetry_cache(self) -> dict[str, Any]:
        """Carga la última telemetría conocida desde disco para poblar de inmediato los sensores al iniciar."""
        try:
            with open(TELEMETRY_CACHE_PATH, "r", encoding="utf-8") as file_handle:
                cached = json.load(file_handle)
            if isinstance(cached, dict):
                if cached.get("productid"):
                    self.product_id = cached["productid"]
                return cached
        except Exception:
            pass
        return {}

    def _save_telemetry_cache(self) -> None:
        """Guarda la última telemetría recibida de forma atómica."""
        try:
            os.makedirs(os.path.dirname(TELEMETRY_CACHE_PATH), exist_ok=True)
            temp_path = TELEMETRY_CACHE_PATH + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as file_handle:
                json.dump(self.last_telemetry, file_handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, TELEMETRY_CACHE_PATH)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Gestión del filtro antidesconexión (resuelve la caída de 5 segundos cada 5 horas)
    # -------------------------------------------------------------------------

    def _cancel_disconnect_timer(self) -> None:
        """Cancela el temporizador de desconexión si la Box se ha reconectado a tiempo."""
        if self.disconnect_timer is not None:
            self.disconnect_timer.cancel()
            self.disconnect_timer = None

    def _schedule_disconnect_notification(self) -> None:
        """Inicia una cuenta atrás antes de notificar la Box como desconectada en HA.

        Cada 5 horas la Connect Box cierra la conexión TLS y la vuelve a abrir tras ~5 segundos.
        Esperando `disconnect_grace_seconds` (por defecto 30s), evitamos falsos estados de 'Desconectado'.
        """
        self._cancel_disconnect_timer()
        grace_seconds = self.config.disconnect_grace_seconds
        if grace_seconds <= 0:
            self._confirm_box_disconnected()
            return

        _log.info(
            "Sessione TLS chiusa dalla Box: attendo %ds per eventuale riconnessione rapida...",
            grace_seconds,
        )
        self.disconnect_timer = threading.Timer(grace_seconds, self._confirm_box_disconnected)
        self.disconnect_timer.daemon = True
        self.disconnect_timer.start()

    def _confirm_box_disconnected(self) -> None:
        """Se ejecuta únicamente si la Box no se ha reconectado dentro del tiempo de tolerancia."""
        with self.box_lock:
            self.disconnect_timer = None
            if self.box_socket is None:
                self.box_connected = False
                _log.warning("Connect Box non riconnessa entro il tempo limite: stato impostato a Disconnesso.")
                self.publish_to_ha(f"{self.config.mqtt_prefix}/health/box_connected", "false")

    # -------------------------------------------------------------------------
    # Comunicación con la Aldes Connect Box (Servidor TLS)
    # -------------------------------------------------------------------------

    def send_command_to_box(self, method: str, params: list[Any]) -> None:
        """Envía un comando JSON-RPC a la Connect Box respetando la pausa mínima de 2 segundos."""
        with self.send_lock:
            elapsed = time.monotonic() - self.last_command_sent_at
            if self.last_command_sent_at > 0 and elapsed < COMMAND_MIN_INTERVAL:
                wait_seconds = COMMAND_MIN_INTERVAL - elapsed
                _log.debug("Comando ravvicinato: attendo %.1fs prima dell'invio...", wait_seconds)
                time.sleep(wait_seconds)

            with self.box_lock:
                self.rpc_command_id += 1
                rpc_body = json.dumps(
                    {
                        "id": self.rpc_command_id,
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params,
                    },
                    ensure_ascii=False,
                )
                topic = f"devices/{self.product_id}/messages/devicebound"
                if not self.box_socket:
                    _log.warning("Comando NON inviato (Connect Box non connessa): %s", rpc_body)
                    return
                self.box_packet_id = (self.box_packet_id % 65530) + 1
                packet = mqtt.build_publish(topic, rpc_body, qos=1, pkt_id=self.box_packet_id)
                try:
                    self.box_socket.sendall(packet)
                    self.last_command_sent_at = time.monotonic()
                    _log.info("--> COMANDO INVIATO ALLA BOX [%s]: %s", topic, rpc_body)
                except Exception as exc:
                    _log.error("Errore durante l'invio del comando alla Box: %s", exc)

    def _cancel_verify_timer(self) -> None:
        """Cancela el temporizador de verificación si el cambio de modo ya ha sido confirmado."""
        if self.verify_timer is not None:
            self.verify_timer.cancel()
            self.verify_timer = None

    def _verify_mode_applied(self, expected_code: str, params: list[Any]) -> None:
        """Comprueba tras 15s si la VMC ha cambiado de modo; en caso contrario reenvía el comando una vez."""
        self.verify_timer = None
        if self.pending_mode_code != expected_code:
            return

        actual_mode = str(self.last_telemetry.get("current_mode") or "").strip().upper()
        self.pending_mode_code = None

        if actual_mode != expected_code:
            _log.warning(
                "La VMC e' ancora in modalita' '%s' invece di '%s' dopo %.0fs: reinvio il comando...",
                actual_mode or "?",
                expected_code,
                COMMAND_VERIFY_TIMEOUT,
            )
            self.send_command_to_box("changeMode", params)

    def run_box_listener(self) -> None:
        """Acepta en bucle continuo las conexiones TLS procedentes de la Connect Box."""
        tls_ctx = server_context("aldesiotsuite.azure-devices.net")
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("0.0.0.0", self.config.listen_port))
        server_sock.listen(4)
        _log.info(
            "=== Aldes Bridge SC150 v%s in ascolto TLS su 0.0.0.0:%d ===",
            __version__,
            self.config.listen_port,
        )
        while True:
            try:
                client_sock, client_addr = server_sock.accept()
                tls_socket = tls_ctx.wrap_socket(client_sock, server_side=True)
                _log.info("Connect Box collegata da %s:%d", client_addr[0], client_addr[1])
                threading.Thread(
                    target=self._handle_box_session,
                    args=(tls_socket,),
                    daemon=True,
                ).start()
            except Exception as exc:
                _log.warning("Handshake TLS con la Box fallito: %s", exc)

    def _handle_box_session(self, tls_socket: socket.socket) -> None:
        """Gestiona los paquetes MQTT de una sesión TLS individual con la Connect Box."""
        with self.box_lock:
            self._cancel_disconnect_timer()
            previous_socket = self.box_socket
            self.box_socket = tls_socket
            self.box_connected = True

        if previous_socket:
            try:
                previous_socket.close()
            except Exception:
                pass

        self.publish_to_ha(f"{self.config.mqtt_prefix}/health/box_connected", "true")
        reader = mqtt.MQTTReader(tls_socket)

        try:
            while True:
                packet = reader.read_packet()
                if packet is None:
                    break
                packet_type, flags, body, _ = packet

                if packet_type == mqtt.PT_CONNECT:
                    connect_info = mqtt.parse_connect(body)
                    if connect_info.get("client_id"):
                        self.product_id = connect_info["client_id"]
                    keepalive = connect_info.get("keepalive", 60)
                    tls_socket.settimeout(max(660, keepalive * 3))
                    tls_socket.sendall(mqtt.build_connack(0))

                elif packet_type == mqtt.PT_SUBSCRIBE:
                    packet_id, subscriptions = mqtt.parse_subscribe(body)
                    for topic_filter, _ in subscriptions:
                        if "devices/" in topic_filter:
                            parts = topic_filter.split("/")
                            if len(parts) > 1 and parts[1]:
                                self.product_id = parts[1]
                    tls_socket.sendall(mqtt.build_suback(packet_id, [min(qos, 2) for _, qos in subscriptions]))

                elif packet_type == mqtt.PT_PINGREQ:
                    tls_socket.sendall(mqtt.build_pingresp())

                elif packet_type == mqtt.PT_PUBLISH:
                    topic, qos, packet_id, raw_payload = mqtt.parse_publish_full(body, flags)
                    if qos == 1:
                        tls_socket.sendall(mqtt.build_puback(packet_id))
                    elif qos == 2:
                        tls_socket.sendall(mqtt.build_pubrec(packet_id))

                    telemetry_data = extract_json_dict(raw_payload)
                    if telemetry_data:
                        if telemetry_data.get("productid"):
                            self.product_id = telemetry_data["productid"]
                        self.last_telemetry.update(telemetry_data)
                        self._save_telemetry_cache()
                        _log.info(
                            "<-- TELEMETRIA [%s]: mode=%s flw=%s/%s m3/h T_out=%s\u00b0C T_in=%s\u00b0C ff_cpt=%s",
                            self.product_id,
                            self.last_telemetry.get("current_mode"),
                            self.last_telemetry.get("extf_flw"),
                            self.last_telemetry.get("ffe_flw"),
                            self.last_telemetry.get("outside_tpt"),
                            self.last_telemetry.get("ext_tpt"),
                            self.last_telemetry.get("ff_cpt"),
                        )
                        self.publish_telemetry(self.last_telemetry)

                elif packet_type == mqtt.PT_PUBREL:
                    packet_id = struct.unpack_from(">H", body)[0] if len(body) >= 2 else 0
                    tls_socket.sendall(mqtt.build_pubcomp(packet_id))

                elif packet_type == mqtt.PT_DISCONNECT:
                    break
        except Exception as exc:
            _log.info(" Connessione TLS chiusa (%s)", exc)
        finally:
            with self.box_lock:
                if self.box_socket is tls_socket:
                    self.box_socket = None
                    self._schedule_disconnect_notification()
            try:
                tls_socket.close()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Publicación de estados y gestión de comandos desde Home Assistant
    # -------------------------------------------------------------------------

    def publish_to_ha(self, topic: str, payload: Any, retain: bool = True) -> None:
        """Publica un mensaje MQTT en el broker Mosquitto de Home Assistant."""
        with self.ha_lock:
            if not self.ha_socket:
                return
            self.ha_packet_id = (self.ha_packet_id % 65530) + 1
            try:
                packet = mqtt.build_publish(
                    topic,
                    str(payload),
                    qos=1,
                    pkt_id=self.ha_packet_id,
                    retain=retain,
                )
                self.ha_socket.sendall(packet)
            except Exception:
                pass

    def publish_telemetry(self, telemetry: dict[str, Any]) -> None:
        """Formatea y publica en Home Assistant todos los sensores y los cálculos del filtro."""
        prefix = self.config.mqtt_prefix

        # 1. Publica los sensores estándar
        for sensor in TELEMETRY_SENSORS:
            if not sensor.is_active:
                continue
            raw_value = telemetry.get(sensor.telemetry_key)
            if raw_value is None:
                continue

            formatted_value = str(raw_value).strip()
            if sensor.value_type == "float":
                try:
                    formatted_value = f"{float(raw_value):.1f}"
                except (ValueError, TypeError):
                    pass
            elif sensor.value_type == "int":
                try:
                    formatted_value = f"{int(round(float(raw_value)))}"
                except (ValueError, TypeError):
                    pass

            self.publish_to_ha(f"{prefix}/state/sensor/{sensor.telemetry_key}", formatted_value)

        # 2. Actualiza y publica las métricas calculadas para los filtros
        filter_info = self.filter_tracker.update_from_telemetry(telemetry.get("ff_cpt"))
        if filter_info is not None:
            self.publish_to_ha(f"{prefix}/state/filter/filter_remaining_days", filter_info.remaining_days)
            self.publish_to_ha(f"{prefix}/state/filter/filter_elapsed_days", filter_info.elapsed_days)
            self.publish_to_ha(f"{prefix}/state/filter/filter_wear_percent", f"{filter_info.wear_percent:.1f}")
            self.publish_to_ha(f"{prefix}/state/filter/filter_last_reset", filter_info.last_reset.isoformat())

        # 3. Sincroniza el selector de modo de la VMC y verifica posibles comandos pendientes
        current_mode = str(telemetry.get("current_mode") or "").strip().upper()
        if self.pending_mode_code and current_mode == self.pending_mode_code:
            _log.info("Verifica superata: la VMC ha confermato il passaggio alla modalita' '%s'", current_mode)
            self._cancel_verify_timer()
            self.pending_mode_code = None
        if current_mode in self.exposed_modes:
            self.publish_to_ha(f"{prefix}/state/select/mode", self.exposed_modes[current_mode])
        elif current_mode in self.all_known_modes:
            _log.debug(
                "Modalita' attiva '%s' (%s) gestita internamente ma non esposta nel selettore",
                current_mode,
                self.all_known_modes[current_mode],
            )

    def apply_operating_mode(self, mode_code: str) -> None:
        """Envía a la VMC la solicitud de cambio de modo (V, Y, X o W) y verifica su resultado."""
        clean_code = mode_code.strip().upper()
        if clean_code == "W":
            start_utc = datetime.now(timezone.utc).replace(microsecond=0)
            end_utc = start_utc + timedelta(days=7)
            date_format = "%Y%m%d%H%M%S"
            params = [f"W{start_utc.strftime(date_format)}Z{end_utc.strftime(date_format)}Z"]
        else:
            params = [clean_code]

        previous_mode = str(self.last_telemetry.get("current_mode") or "").strip().upper()
        self._cancel_verify_timer()
        self.send_command_to_box("changeMode", params)

        # Inicia la verificación solo si se está cambiando hacia un modo distinto del actual
        if previous_mode != clean_code:
            self.pending_mode_code = clean_code
            self.verify_timer = threading.Timer(
                COMMAND_VERIFY_TIMEOUT,
                self._verify_mode_applied,
                args=(clean_code, params),
            )
            self.verify_timer.daemon = True
            self.verify_timer.start()

        prefix = self.config.mqtt_prefix
        if clean_code in self.exposed_modes:
            self.publish_to_ha(f"{prefix}/state/select/mode", self.exposed_modes[clean_code])
        self.publish_to_ha(f"{prefix}/state/sensor/current_mode", clean_code)

    # Alias de compatibilidad con posibles scripts de prueba
    _apply_mode = apply_operating_mode

    def _handle_ha_command(self, topic: str, payload: str) -> None:
        """Interpreta los comandos recibidos desde Home Assistant (selector o botones)."""
        clean_payload = payload.strip()
        _log.info("Comando ricevuto da Home Assistant [%s]: %s", topic, clean_payload)

        if topic.endswith("/select/mode"):
            mode_code = self.label_to_mode_code.get(clean_payload.lower())
            if mode_code:
                self.apply_operating_mode(mode_code)
        elif topic.endswith("/button/mode_v"):
            self.apply_operating_mode("V")
        elif topic.endswith("/button/mode_y"):
            self.apply_operating_mode("Y")
        elif topic.endswith("/button/mode_x"):
            self.apply_operating_mode("X")
        elif topic.endswith("/button/mode_w"):
            self.apply_operating_mode("W")

    def run_ha_mqtt_loop(self) -> None:
        """Mantiene activa la conexión hacia el broker Mosquitto de Home Assistant."""
        host, port, username, password = detect_mqtt_broker(self.config)
        prefix = self.config.mqtt_prefix

        while True:
            try:
                _log.info("Connessione a Mosquitto (%s:%d, user=%s)...", host, port, username or "nessuno")
                sock = socket.create_connection((host, port), timeout=6)
                sock.settimeout(15)
                reader = mqtt.MQTTReader(sock)

                sock.sendall(
                    mqtt.build_connect(
                        "aldes-sc150-bridge",
                        username=username,
                        password=password,
                        keepalive=30,
                        will_topic=f"{prefix}/state/available",
                        will_payload="offline",
                        will_qos=1,
                        will_retain=True,
                    )
                )
                connack = reader.read_packet()
                if not connack or connack[0] != mqtt.PT_CONNACK or (len(connack[3]) > 2 and connack[3][2] != 0):
                    return_code = connack[3][2] if (connack and len(connack[3]) > 2) else -1
                    _log.error("CONNACK rifiutato da Mosquitto (rc=%d).", return_code)
                    sock.close()
                    time.sleep(5)
                    continue

                with self.ha_lock:
                    self.ha_socket = sock

                sock.sendall(mqtt.build_subscribe(1, [(f"{prefix}/set/#", 1)]))
                publish_homeassistant_discovery(self)
                if self.last_telemetry:
                    self.publish_telemetry(self.last_telemetry)

                _log.info("Connesso a Mosquitto: Auto-Discovery v%s pubblicata con successo!", __version__)
                last_ping_time = time.time()

                while True:
                    try:
                        packet = reader.read_packet()
                    except socket.timeout:
                        if time.time() - last_ping_time >= 15:
                            with self.ha_lock:
                                sock.sendall(mqtt.build_pingreq())
                            last_ping_time = time.time()
                        continue

                    if packet is None:
                        break
                    packet_type, flags, body, _ = packet
                    if packet_type == mqtt.PT_PUBLISH:
                        msg_topic, qos, packet_id, raw_msg = mqtt.parse_publish_full(body, flags)
                        if qos == 1:
                            with self.ha_lock:
                                sock.sendall(mqtt.build_puback(packet_id))
                        self._handle_ha_command(msg_topic, raw_msg.decode("utf-8", errors="replace"))
            except Exception as exc:
                _log.warning("Disconnesso da Mosquitto (%s), nuovo tentativo tra 5s...", exc)
            finally:
                with self.ha_lock:
                    self.ha_socket = None
            time.sleep(5)
