# Aldes Bridge SC150 — Home Assistant Add-on

![Version](https://img.shields.io/badge/version-2.2.2-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Arch](https://img.shields.io/badge/arch-amd64%20%7C%20aarch64-orange.svg)

**[Español](#espanol) | [English](#english)**

---

<a name="espanol"></a>
## Español

Complemento (add-on) nativo para **Home Assistant** que permite el control **100% local** y la monitorización completa de la unidad de VMC **Aldes InspirAIR Home SC150** (a través de **Aldes Connect Box**), eliminando por completo la dependencia de los servidores en la nube de Aldes.

> **Aviso legal / Exclusión de responsabilidad**
> Este complemento es un proyecto independiente de código abierto desarrollado con fines personales y educativos. **El autor no está de ninguna manera afiliado, asociado, autorizado, patrocinado ni conectado oficialmente con Aldes** (ni con ninguna de sus filiales o empresas asociadas).
> El uso de este software se realiza bajo su propio riesgo. El autor no asume ninguna responsabilidad por posibles fallos de funcionamiento, bloqueos del sistema, pérdida de datos o daños en la unidad VMC Aldes InspirAIR Home SC150, el módulo Aldes Connect Box, la instalación eléctrica o de climatización, o la instalación de Home Assistant derivados del uso de este complemento.

### Características Principales

- **Control 100% Local (Sin Nube):** Intercepta el tráfico MQTT sobre TLS (puerto `8883` redirigido localmente al `18883`) que la Connect Box envía hacia `aldesiotsuite.azure-devices.net`, gestionando la telemetría y los comandos directamente dentro de la red local.
- **Auto-Discovery MQTT Nativo:** Detecta automáticamente el broker Mosquitto de Home Assistant a través de la API del Supervisor y registra todas las entidades sin necesidad de configuración manual en `configuration.yaml`.
- **Selector de Modo de Funcionamiento (`select`):** Control directo de los modos de ventilación admitidos por la VMC:
  * **Diario (`V`)**
  * **Cocina (`Y`)**
  * **Boost (`X`)**
  * **Vacaciones (`W`)** — con generación automática de la ventana temporal concatenada en formato UTC (`W<inicio_UTC>Z<fin_UTC>Z`).
- **Verificación de Comandos y Protección Serie:** Incluye un intervalo mínimo de seguridad (2 segundos) entre paquetes JSON-RPC para no saturar la comunicación serie UART del módulo Wi-Fi (`HF-LPB100`), junto con un sistema de verificación automática que reenvía el comando si la unidad no confirma el cambio de modo en un plazo de 15 segundos.
- **Estabilidad de Conexión (Grace Timer y Timeout Extendido):**
  * **Grace Timer (30s):** Enmascara las microdesconexiones normales de ~5 segundos que realiza la Connect Box cada 5 horas al renovar el token de sesión, evitando estados falsos de `Desconectado` en el historial de Home Assistant.
  * **Timeout TLS de 660s:** Calibrado según el intervalo de envío de telemetría de la unidad (10 minutos) para evitar desconexiones por tiempo de espera de lectura.
- **Monitorización Inteligente de Filtros (`FilterTracker`):** Detecta automáticamente la puesta a cero del contador `ff_cpt` realizada desde la pantalla física de la VMC tras sustituir los filtros, guardando la marca temporal en disco (`/config/aldes/filters.json`) y calculando de forma autónoma los días transcurridos, los días restantes y el porcentaje estimado de desgaste.

### Requisito de Red (DNS Local)

La Aldes Connect Box intenta conectarse al dominio en la nube `aldesiotsuite.azure-devices.net` en el puerto TCP `8883`.
Para redirigir el tráfico hacia Home Assistant sin modificar físicamente la Connect Box, es necesario configurar una regla de **reescritura DNS (DNS Rewrite)** en su servidor DNS local (por ejemplo, **AdGuard Home**, **Pi-hole**, **UniFi**, **MikroTik** o un router compatible):

```text
aldesiotsuite.azure-devices.net  --->  <DIRECCION_IP_HOME_ASSISTANT>
```

Al iniciarse, el complemento aplica automáticamente una regla `iptables` (`PREROUTING`) que reenvía los paquetes entrantes del puerto `8883` al puerto interno `18883` del puente TLS.

### Instalación en Home Assistant

1. En Home Assistant, ve a **Ajustes** → **Complementos** → **Tienda de complementos**.
2. Haz clic en los **tres puntos** de la esquina superior derecha y selecciona **Repositorios**.
3. Pega la URL de este repositorio:
   ```text
   https://github.com/David-PLC/aldes-bridge-sc150
   ```
4. Haz clic en **Añadir** y luego cierra la ventana.
5. Busca **Aldes Bridge SC150** en la lista de complementos, haz clic en **Instalar** y activa las opciones **Iniciar en el arranque** y **Watchdog**.

### Configuración

El complemento funciona directamente con los valores predeterminados (detecta automáticamente el broker `core-mosquitto` de Home Assistant). Desde la pestaña **Configuración** del complemento se pueden personalizar los siguientes parámetros:

| Opción | Valor por defecto | Descripción |
| :--- | :---: | :--- |
| `mqtt_port` | `18883` | Puerto local en el que el servidor TLS escucha a la Connect Box (redirige `8883` → `18883`). |
| `box_ip` | `""` | *(Opcional)* Dirección IP de la Connect Box para limitar la regla `iptables` únicamente al tráfico procedente de la VMC. |
| `filter_months` | `6` | Vida útil nominal de los filtros en meses (`6` meses = 180 días) utilizada para calcular los días restantes. |
| `language` | `"it"` | Idioma utilizado para los nombres de las entidades generadas en Home Assistant (`translations/<lang>.json`). |
| `ha_mqtt_host` | `""` | *(Opcional)* Host del broker MQTT. Déjalo vacío para la detección automática mediante la API del Supervisor. |
| `ha_mqtt_port` | `1883` | Puerto TCP del broker MQTT de Home Assistant. |
| `ha_mqtt_user` | `""` | *(Opcional)* Nombre de usuario MQTT (si no lo gestiona automáticamente el Supervisor). |
| `ha_mqtt_password` | `""` | *(Opcional)* Contraseña MQTT (si no la gestiona automáticamente el Supervisor). |

### Entidades Expuestas en Home Assistant

#### Control y Conectividad
- **Modo VMC (`select`)** — Selector de modo (`Diario` / `V`, `Cocina` / `Y`, `Boost` / `X`, `Vacaciones` / `W`)
- **Conectividad Connect Box (`binary_sensor`)** — Estado de la conexión TLS de la Aldes Connect Box

#### Monitorización de Filtros
- **Días Restantes de Filtro (`sensor`)** — Días restantes antes del reemplazo del filtro
- **Días de Uso de Filtro (`sensor`)** — Días transcurridos desde el último reinicio detectado
- **Desgaste Estimado de Filtro (`sensor`)** — Porcentaje de desgaste calculado según `filter_months`
- **Último Reinicio de Filtro (`sensor`)** — Fecha y hora del último cambio o reinicio de filtro detectado
- **Contador de Filtro Box (`sensor`)** — Valor bruto `ff_cpt` enviado por la Connect Box
- **Índice de Depresión de Filtros (`sensor`)** — Indicador de pérdida de carga (`dep_ind`)

#### Temperaturas, Caudales y Ventilación
- **Temperatura de Aire Exterior** (`outside_tpt`, °C)
- **Temperatura de Aire Extraído** (`ext_tpt`, °C)
- **Temperatura de Aire Expulsado** (`reject_tpt`, °C)
- **Caudal de Extracción** (`extf_flw`, m³/h)
- **Caudal de Impulsión** (`ffe_flw`, m³/h)
- **Velocidad del Ventilador de Extracción** (`extf_spd`, rpm)
- **Velocidad del Ventilador de Impulsión** (`vi_spd`, rpm)
- **Nivel de Velocidad VMC** (`set_spd`)
- **Estado del Bypass** (`dtb_ind`)
- **Código de Modo Activo** (`current_mode`)
- **Versión de Firmware UC / Wi-Fi** (`Vers_UC` / `Vers_W`)

*(Los sensores opcionales para sondas accesorias de CO2, PM2.5, COV y consumo eléctrico se registran pero permanecen deshabilitados por defecto para mantener limpia la interfaz; pueden habilitarse manualmente desde Home Assistant si están instalados en el sistema).*

### Arquitectura del Código

El proyecto está organizado en módulos de Python independientes y documentados dentro de `aldes-bridge/server/`:

- `main.py` — Punto de entrada del complemento y gestión de señales del sistema operativo.
- `bridge.py` — Gestión de la sesión TLS con la Connect Box, bucle MQTT hacia Home Assistant, verificación de comandos y Grace Timer.
- `discovery.py` — Generación y limpieza de los payloads de Auto-Discovery MQTT para Home Assistant.
- `filters.py` — Lógica de cálculo de desgaste de filtros y detección automática de reinicios desde la pantalla física (`FilterTracker`).
- `models.py` — Catálogo estructurado (`SensorDefinition`) de los sensores de telemetría.
- `config.py` — Carga de variables de entorno, traducciones JSON y detección automática del broker Mosquitto.
- `mqtt.py` / `tls.py` — Códec ligero MQTT 3.1.1 y generación del contexto TLS compatible con el módulo Wi-Fi `HF-LPB100`.

---

<a name="english"></a>
## English

Native **Home Assistant** add-on providing **100% local control** and full telemetry monitoring for the **Aldes InspirAIR Home SC150** heat recovery ventilation unit (via **Aldes Connect Box**), completely eliminating reliance on Aldes cloud servers.

> **Disclaimer**
> This add-on is an independent, hobbyist open-source project. **The author is in no way affiliated with, associated with, authorized, sponsored by, or officially connected to Aldes** (or any of its subsidiaries or affiliates).
> Use of this software is entirely at your own risk. The author assumes no responsibility or liability for any malfunctions, system lockups, data loss, or damage to the Aldes InspirAIR Home SC150 unit, the Aldes Connect Box module, your electrical/HVAC system, or your Home Assistant installation resulting from the use of this add-on.

### Key Features

- **100% Local Control (Cloud-Free):** Intercepts the MQTT over TLS traffic (port `8883` locally redirected to `18883`) sent by the Connect Box to `aldesiotsuite.azure-devices.net`, handling telemetry and commands directly within your local network.
- **Native MQTT Auto-Discovery:** Automatically detects Home Assistant's Mosquitto broker via the Supervisor API and registers all entities without requiring manual configuration in `configuration.yaml`.
- **Operating Mode Selector (`select`):** Direct control over the supported ventilation modes:
  * **Daily (`V`)**
  * **Kitchen (`Y`)**
  * **Boost (`X`)**
  * **Holidays (`W`)** — featuring automatic generation of the concatenated UTC time window string (`W<start_UTC>Z<end_UTC>Z`).
- **Command Verification & Serial Protection:** Enforces a 2-second safety interval between JSON-RPC packets to avoid flooding the Wi-Fi module's (`HF-LPB100`) UART serial line, coupled with an automatic verification system that resends the command if the unit does not confirm the mode change within 15 seconds.
- **Connection Stability (Grace Timer & Extended Timeout):**
  * **Grace Timer (30s):** Masks the normal ~5-second reconnections performed by the Connect Box every 5 hours during session token renewal, preventing false `Disconnected` states in Home Assistant's history.
  * **660s TLS Timeout:** Matched to the unit's 10-minute telemetry reporting interval to prevent read-timeout disconnections.
- **Smart Filter Monitoring (`FilterTracker`):** Automatically detects when the `ff_cpt` counter is reset from the unit's physical display after filter replacement, persisting the reset timestamp to disk (`/config/aldes/filters.json`) and calculating elapsed days, remaining days, and estimated wear percentage.

### Network Prerequisite (Local DNS)

The Aldes Connect Box connects to the cloud hostname `aldesiotsuite.azure-devices.net` on TCP port `8883`.
To route traffic to Home Assistant without physically modifying the Connect Box, configure a **DNS Rewrite** rule on your local DNS server (e.g., **AdGuard Home**, **Pi-hole**, **UniFi**, **MikroTik**, or a compatible router):

```text
aldesiotsuite.azure-devices.net  --->  <HOME_ASSISTANT_IP_ADDRESS>
```

At startup, the add-on automatically applies an `iptables` (`PREROUTING`) rule that forwards incoming packets on port `8883` to the internal TLS bridge port `18883`.

### Installation on Home Assistant

1. In Home Assistant, navigate to **Settings** → **Add-ons** → **Add-on Store**.
2. Click the **three dots** in the top-right corner and select **Repositories**.
3. Paste the URL of this repository:
   ```text
   https://github.com/David-PLC/aldes-bridge-sc150
   ```
4. Click **Add**, then close the dialog.
5. Find **Aldes Bridge SC150** in the add-on list, click **Install**, and enable **Start on boot** and **Watchdog**.

### Configuration

The add-on works out of the box with default settings (auto-detecting Home Assistant's `core-mosquitto` broker). You can customize the following parameters in the add-on's **Configuration** tab:

| Option | Default | Description |
| :--- | :---: | :--- |
| `mqtt_port` | `18883` | Local port where the TLS server listens for the Connect Box (redirects `8883` → `18883`). |
| `box_ip` | `""` | *(Optional)* IP address of the Connect Box to restrict the `iptables` rule exclusively to VMC traffic. |
| `filter_months` | `6` | Nominal filter lifespan in months (`6` months = 180 days) used to calculate remaining days. |
| `language` | `"it"` | Language used for entity names generated in Home Assistant (`translations/<lang>.json`). |
| `ha_mqtt_host` | `""` | *(Optional)* MQTT broker host. Leave empty for automatic discovery via the Supervisor API. |
| `ha_mqtt_port` | `1883` | TCP port of the Home Assistant MQTT broker. |
| `ha_mqtt_user` | `""` | *(Optional)* MQTT username (if not automatically managed by the Supervisor). |
| `ha_mqtt_password` | `""` | *(Optional)* MQTT password (if not automatically managed by the Supervisor). |

### Exposed Entities in Home Assistant

#### Control & Connectivity
- **VMC Mode (`select`)** — Mode selector (`Daily` / `V`, `Kitchen` / `Y`, `Boost` / `X`, `Holidays` / `W`)
- **Connect Box Connectivity (`binary_sensor`)** — TLS connection status of the Aldes Connect Box

#### Filter Monitoring
- **Filter Remaining Days (`sensor`)** — Days remaining before filter replacement
- **Filter Elapsed Days (`sensor`)** — Days elapsed since the last detected filter reset
- **Filter Estimated Wear (`sensor`)** — Calculated wear percentage based on `filter_months`
- **Filter Last Reset (`sensor`)** — Timestamp of the last detected filter change/reset
- **Box Filter Counter (`sensor`)** — Raw `ff_cpt` value reported by the Connect Box
- **Filter Pressure Drop Index (`sensor`)** — Pressure drop indicator (`dep_ind`)

#### Temperatures, Airflow & Fan Speeds
- **Outdoor Air Temperature** (`outside_tpt`, °C)
- **Extract Air Temperature** (`ext_tpt`, °C)
- **Exhaust Air Temperature** (`reject_tpt`, °C)
- **Extract Airflow** (`extf_flw`, m³/h)
- **Supply Airflow** (`ffe_flw`, m³/h)
- **Extract Fan Speed** (`extf_spd`, rpm)
- **Supply Fan Speed** (`vi_spd`, rpm)
- **VMC Speed Level** (`set_spd`)
- **Bypass Status** (`dtb_ind`)
- **Active Mode Code** (`current_mode`)
- **UC / Wi-Fi Firmware Version** (`Vers_UC` / `Vers_W`)

*(Optional sensors for accessory CO2, PM2.5, VOC probes, and electrical power consumption are registered but disabled by default to keep the UI clean; they can be manually enabled in Home Assistant if installed on your system).*

### Code Architecture

The project is organized into clean, documented Python modules inside `aldes-bridge/server/`:

- `main.py` — Add-on entry point and OS signal handling.
- `bridge.py` — TLS session handler for the Connect Box, Home Assistant MQTT loop, command verification, and Grace Timer.
- `discovery.py` — Generation and cleanup of Home Assistant MQTT Auto-Discovery payloads.
- `filters.py` — Filter wear calculation and automatic physical reset detection (`FilterTracker`).
- `models.py` — Structured telemetry sensor catalog (`SensorDefinition`).
- `config.py` — Environment configuration loader, JSON translations, and automatic Mosquitto broker detection.
- `mqtt.py` / `tls.py` — Lightweight MQTT 3.1.1 codec and legacy-compatible TLS context for the `HF-LPB100` Wi-Fi module.

---

## Reconocimientos / Acknowledgements

Este proyecto nace y evoluciona gracias al trabajo de ingeniería inversa y a las contribuciones de la comunidad de código abierto / This project builds upon the reverse engineering and open-source contributions of the community:

- **[saniho/aldes-bridge](https://github.com/saniho/aldes-bridge)** — Por el análisis original del protocolo de comunicación TLS/MQTT de la Aldes Connect Box, la decodificación de los métodos JSON-RPC y el concepto de interceptación local / *For the original reverse engineering of the Aldes Connect Box TLS/MQTT protocol, JSON-RPC method decoding, and local interception concept.*
- **[Conedo95/aldes_vmc](https://github.com/Conedo95/aldes_vmc)** — Por la inspiración arquitectónica y la lógica de seguimiento automático del reinicio de filtros (`ff_cpt`) adaptada en el módulo `filters.py` / *For architectural inspiration and the automatic filter reset tracking logic (`ff_cpt`) adapted in `filters.py`.*

---

## Licencia / License

Este proyecto se distribuye bajo la licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para ver el texto completo de los términos de uso.  
This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for full details.
