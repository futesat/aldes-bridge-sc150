"""Gestión de la configuración del complemento, de las traducciones y del broker MQTT."""
import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger("aldes-sc150")

# Rutas de los archivos persistentes guardados en la carpeta de configuración del complemento
TELEMETRY_CACHE_PATH = "/config/aldes/telemetry.json"
FILTER_STORAGE_PATH = "/config/aldes/filters.json"
APP_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class BridgeConfig:
    """Contiene todos los parámetros de inicio leídos desde las variables de entorno."""

    listen_port: int = 18883
    mqtt_prefix: str = "aldes"
    language: str = "it"
    filter_months: int = 6
    # Tiempo de espera (en segundos) antes de declarar la Connect Box como desconectada.
    # Evita falsas alarmas cada 5 horas cuando la Box renueva la sesión TLS en 5 segundos.
    disconnect_grace_seconds: int = 30
    ha_mqtt_host: str = ""
    ha_mqtt_port: int = 1883
    ha_mqtt_user: Optional[str] = None
    ha_mqtt_password: Optional[str] = None

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        """Crea la configuración leyendo las variables exportadas por run.sh."""
        return cls(
            listen_port=int(os.environ.get("MQTT_PORT") or 18883),
            mqtt_prefix="aldes",
            language=(os.environ.get("ALDES_LANG") or "it").strip(),
            filter_months=int(os.environ.get("FILTER_MONTHS") or 6),
            disconnect_grace_seconds=int(os.environ.get("DISCONNECT_GRACE_SECONDS") or 30),
            ha_mqtt_host=(os.environ.get("HA_MQTT_HOST") or "").strip(),
            ha_mqtt_port=int(os.environ.get("HA_MQTT_PORT") or 1883),
            ha_mqtt_user=(os.environ.get("HA_MQTT_USER") or "").strip() or None,
            ha_mqtt_password=(os.environ.get("HA_MQTT_PASSWORD") or "").strip() or None,
        )


def load_translations(language: str = "it") -> dict:
    """Carga el diccionario de nombres de entidades desde el archivo JSON del idioma elegido."""
    file_path = os.path.join(APP_ROOT_DIR, "translations", f"{language}.json")
    if not os.path.isfile(file_path):
        file_path = os.path.join(APP_ROOT_DIR, "translations", "it.json")
    try:
        with open(file_path, "r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except Exception as exc:
        _log.warning("Impossibile caricare il file traduzioni %s (%s), uso nomi di default", file_path, exc)
        return {}


def detect_mqtt_broker(config: BridgeConfig) -> tuple[str, int, Optional[str], Optional[str]]:
    """Devuelve (host, port, username, password) del broker MQTT de Home Assistant.

    Si el usuario no ha introducido manualmente el host en la pestaña Configuración,
    consulta la API interna del Supervisor de Home Assistant para obtener los datos de Mosquitto.
    """
    if config.ha_mqtt_host:
        return config.ha_mqtt_host, config.ha_mqtt_port, config.ha_mqtt_user, config.ha_mqtt_password

    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if supervisor_token:
        try:
            request = urllib.request.Request(
                "http://supervisor/services/mqtt",
                headers={"Authorization": f"Bearer {supervisor_token}"},
            )
            with urllib.request.urlopen(request, timeout=4) as response:
                service_data = json.loads(response.read()).get("data", {})
                if service_data.get("host"):
                    detected_host = service_data["host"]
                    detected_port = int(service_data.get("port", 1883))
                    _log.info("Broker MQTT rilevato via Supervisor API: %s:%d", detected_host, detected_port)
                    return (
                        detected_host,
                        detected_port,
                        config.ha_mqtt_user or service_data.get("username"),
                        config.ha_mqtt_password or service_data.get("password"),
                    )
        except Exception as exc:
            _log.warning("Rilevamento automatico Supervisor MQTT non riuscito: %s", exc)

    return "core-mosquitto", config.ha_mqtt_port, config.ha_mqtt_user, config.ha_mqtt_password
