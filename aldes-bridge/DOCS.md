# Aldes Bridge SC150 — Home Assistant Add-on

Complemento (add-on) nativo para **Home Assistant OS** que permite el control y la monitorización **100% local** (sin ninguna dependencia de la nube de Aldes ni de Microsoft Azure) de la unidad VMC de doble flujo **Aldes InspirAIR Home SC150** equipada con el módulo **Aldes Connect Box**.

---

## Índice
1. [Arquitectura y Funcionamiento](#1-arquitectura-y-funcionamiento)
2. [Requisitos de Red (DNS y MQTT)](#2-requisitos-de-red-dns-y-mqtt)
3. [Instalación en Home Assistant](#3-instalación-en-home-assistant)
4. [Configuración del Complemento](#4-configuración-del-complemento)
5. [Entidades Expuestas en Home Assistant](#5-entidades-expuestas-en-home-assistant)
6. [Personalización de Nombres y Traducciones](#6-personalización-de-nombres-y-traducciones)
7. [Seguridad y Permisos (Security Rating)](#7-seguridad-y-permisos-security-rating)
8. [Resolución de Problemas (Troubleshooting)](#8-resolución-de-problemas-troubleshooting)

---

## 1. Arquitectura y Funcionamiento

La **Aldes Connect Box** se comunica de forma nativa con la infraestructura en la nube Azure IoT Hub (`aldesiotsuite.azure-devices.net`) mediante una conexión **MQTT sobre TLS** en el puerto TCP **8883**.

```text
[VMC InspirAIR SC150] <---> [Aldes Connect Box]
                                    |
                     (DNS local: aldesiotsuite.azure-devices.net)
                                    |
                             Puerto TCP 8883 (TLS)
                                    v
                       [Add-on Aldes Bridge SC150]
                        (iptables 8883 -> 18883)
                                    |
                           Puerto TCP 1883 (MQTT)
                                    v
                     [Mosquitto Broker -> Home Assistant]
```

El complemento realiza automáticamente las siguientes operaciones:
* **Emulación del Endpoint TLS de Azure**: genera al iniciarse un certificado X.509 autofirmado para el Common Name `aldesiotsuite.azure-devices.net`, habilitando la compatibilidad con los conjuntos de cifrado heredados requeridos por el firmware de la Connect Box (`TLSv1` / `SECLEVEL=0`).
* **Interceptación del Puerto 8883**: mediante una regla `iptables` (`PREROUTING`), redirige el tráfico TCP entrante en el puerto `8883` hacia el puerto interno `18883` del puente, evitando conflictos con otros servicios del host.
* **Auto-Discovery MQTT para Home Assistant**: se autentica automáticamente en el broker Mosquitto a través de la API del Supervisor de Home Assistant y registra todas las entidades de la VMC bajo un único dispositivo (**Aldes InspirAIR Home SC150**).
* **Control Bidireccional JSON-RPC**: envía los comandos de cambio de modo (`changeMode`) en el topic `devices/<PRODUCT_ID>/messages/devicebound` con confirmación inmediata del estado.
* **Caché Persistente**: guarda la última telemetría recibida en `/config/aldes/telemetry.json`, restaurando de forma instantánea los valores de los sensores incluso tras reiniciar el complemento o Home Assistant.

---

## 2. Requisitos de Red (DNS y MQTT)

Antes de iniciar el complemento, asegúrate de contar con lo siguiente:

1. **Mosquitto Broker activo en Home Assistant**:
   * Instalado como complemento oficial (*Ajustes -> Complementos -> Mosquitto broker*) e integrado en *Ajustes -> Dispositivos y servicios -> MQTT*.

2. **Redirección DNS local para `aldesiotsuite.azure-devices.net`**:
   * El servidor DNS de tu red local (**Pi-hole**, **AdGuard Home**, **Unbound**, **Dnsmasq** o router) debe resolver el dominio en la nube de Aldes hacia la **dirección IP local de Home Assistant**:
     ```text
     aldesiotsuite.azure-devices.net  --->  <IP_HOME_ASSISTANT>
     ```
   * **Nota para usuarios de Pi-hole / Fritz!Box**:
     * Añade el dominio en **Pi-hole -> Local DNS -> DNS Records** asociándolo a la IP de Home Assistant.
     * Asegúrate de que la Aldes Connect Box utilice exclusivamente Pi-hole como servidor DNS (evitando servidores DNS secundarios públicos como `8.8.8.8`).
     * Tras crear la regla en Pi-hole, vacía la caché DNS (`pihole restartdns`) y reinicia eléctricamente la Connect Box para forzar una nueva consulta DNS y la apertura del socket TLS hacia Home Assistant.

---

## 3. Instalación en Home Assistant

1. Abre Home Assistant y ve a **Ajustes** -> **Complementos**.
2. Haz clic en el botón **Tienda de complementos** (abajo a la derecha).
3. Haz clic en el icono de los **tres puntos** (arriba a la derecha) y selecciona **Repositorios**.
4. Pega la URL de este repositorio de GitHub y haz clic en **Añadir**:
   ```text
   https://github.com/David-PLC/aldes-bridge-sc150
   ```
5. Cierra la ventana de repositorios, recarga la página de la tienda y localiza **Aldes Bridge SC150**.
6. Haz clic en **Instalar**, configura las opciones deseadas en la pestaña **Configuración** y pulsa **Iniciar**.

---

## 4. Configuración del Complemento

En la pestaña **Configuración** del complemento están disponibles los siguientes parámetros:

| Parámetro | Valor por defecto | Descripción |
| :--- | :--- | :--- |
| `mqtt_port` | `18883` | Puerto TCP interno en el que escucha el servidor TLS del puente. El script de inicio redirige automáticamente el puerto `8883` hacia este valor mediante `iptables`. |
| `box_ip` | `""` *(vacío)* | **Recomendado**: introduce la dirección IP estática de tu Aldes Connect Box (por ejemplo, `192.168.179.73`). De este modo, la regla `iptables` interceptará únicamente los paquetes procedentes de la VMC. Si se deja vacío, aceptará conexiones en el puerto 8883 desde cualquier IP de la LAN. |
| `filter_months` | `6` | Duración nominal de los filtros en meses (`6` meses = 180 días) utilizada para calcular los días restantes. |
| `language` | `"it"` | Código de idioma utilizado para cargar las etiquetas de los sensores y modos desde el archivo `translations/<language>.json`. |
| `ha_mqtt_host` | `""` *(vacío)* | Host del broker MQTT. Déjalo vacío para utilizar la detección automática mediante Home Assistant Supervisor (`core-mosquitto`). |
| `ha_mqtt_port` | `1883` | Puerto TCP del broker MQTT de Home Assistant. |
| `ha_mqtt_user` | `""` *(vacío)* | Usuario MQTT. Déjalo vacío para utilizar las credenciales proporcionadas automáticamente por el Supervisor, o especifica un usuario dedicado de Mosquitto. |
| `ha_mqtt_password` | `""` *(vacío)* | Contraseña MQTT. Déjalo vacío para utilizar las credenciales del Supervisor. |

---

## 5. Entidades Expuestas en Home Assistant

Todas las entidades se agrupan automáticamente bajo el dispositivo **Aldes InspirAIR Home SC150** en la integración MQTT:

### Controles de Funcionamiento
* **Selector de Modo (`select`) — *Modalità VMC***:
  * **Quotidiano / Diario** (Código `V`): funcionamiento estándar a caudal nominal.
  * **Cucina / Cocina** (Código `Y`): caudal incrementado temporizado para extracción intensiva en cocina.
  * **Boost** (Código `X`): caudal máximo temporizado.
  * **Vacanze / Vacaciones** (Código `W`): caudal mínimo para ausencias prolongadas (establece automáticamente el intervalo de fechas UTC requerido por el protocolo de Aldes).
  * *(El modo `Z` - Programa de aire se gestiona internamente en el código para evitar errores de estado si se activa de forma remota, pero no se expone en el menú desplegable).*
* **Botones Rápidos (`button`)**:
  * **Modo Diario (V)**
  * **Modo Cocina (Y)**
  * **Modo Boost (X)**
  * **Modo Vacaciones (W)**

### Sensores Activos por Defecto
| Clave del Payload | Nombre de Entidad por defecto (`it.json`) | Unidad | Descripción |
| :--- | :--- | :--- | :--- |
| `outside_tpt` | Temperatura Aria Esterna | `°C` | Temperatura del aire exterior aspirado por la VMC. |
| `ext_tpt` | Temperatura Aria Estratta | `°C` | Temperatura del aire interior extraído de las estancias. |
| `reject_tpt` | Temperatura Aria Espulsa | `°C` | Temperatura del aire expulsado al exterior tras pasar por el intercambiador. |
| `extf_flw` | Portata Estrazione | `m³/h` | Caudal volumétrico instantáneo en el conducto de extracción. |
| `ffe_flw` | Portata Insufflazione | `m³/h` | Caudal volumétrico instantáneo en el conducto de impulsión. |
| `extf_spd` | Velocità Ventola Estrazione | `rpm` | Revoluciones por minuto del ventilador de extracción. |
| `vi_spd` | Velocità Ventola Insufflazione | `rpm` | Revoluciones por minuto del ventilador de impulsión. |
| `set_spd` | Livello Velocità VMC | `1–3` | Nivel de velocidad activo. |
| `current_mode` | Codice Modalità Attiva | Texto | Letra bruta del modo actual (`V`, `Y`, `X`, `W`, `Z`). |
| `ff_cpt` | Contatore Usura Filtro (Box) | `%` | Contador bruto de desgaste del filtro reportado por la Connect Box. |
| `dep_ind` | Indice Depressione Filtri | Entero | Índice de pérdida de carga / saturación de filtros. |
| `dtb_ind` | Stato Bypass | Entero | Estado de apertura de la compuerta de bypass (`0` = cerrado). |
| `Vers_UC` | Versione Firmware UC | Entero | Versión de firmware de la placa electrónica de la Unidad Central. |
| `Vers_W` | Versione Firmware Wi-Fi | Texto | Versión de firmware del módulo Aldes Connect Box. |
| — | Connessione Connect Box | `on`/`off` | `binary_sensor` que indica si la Connect Box está conectada por TLS al puente. |

### Sensores Deshabilitados por Defecto
En la **InspirAIR Home SC150** sin accesorios opcionales (como el sensor ambiental Aldes Walter o el módulo de medición de consumo), estas claves devuelven `0` fijo. Se crean **deshabilitadas por defecto** para mantener limpia la interfaz (pudiendo habilitarse en cualquier momento desde Home Assistant):
* `Co2_vmc` (CO2 VMC, `ppm`)
* `Pm25_Vmc` (PM2.5 VMC, `µg/m³`)
* `Voc_Vmc` (VOC VMC, `ppm`)
* `cve_csn` (Consumo Ventilador Extracción, `W`)
* `vi_csn` (Consumo Ventilador Impulsión, `W`)
* `tte_csn` (Consumo Total VMC, `W`)
* `echange_pwr` (Potencia Intercambiador, `W`)

*(El sensor `RSSI`, que en la Connect Box devuelve la cadena fija `--%%`, se mantiene en el código fuente con el indicador `is_active=False` y se elimina automáticamente de Home Assistant).*

---

## 6. Personalización de Nombres y Traducciones

Todos los nombres mostrados en Home Assistant están separados del código Python y residen en el archivo **`aldes-bridge/translations/it.json`**.

Si deseas renombrar un sensor o crear una nueva traducción (por ejemplo, `es.json`, `en.json` o `fr.json`):
1. Modifica las etiquetas en el archivo `aldes-bridge/translations/it.json` (o crea un nuevo archivo `<codigo_idioma>.json` con la misma estructura).
2. Incrementa el número de `version` en `aldes-bridge/config.yaml` y sube los cambios a GitHub.
3. Actualiza el complemento desde Home Assistant.

---

## 7. Seguridad y Permisos (Security Rating)

El complemento incluye un perfil **AppArmor** dedicado (`aldes-bridge/apparmor.txt`) y solicita exclusivamente los privilegios estrictamente indispensables:
* `host_network: true` y `privileged: [NET_ADMIN]`: necesarios para aplicar la regla `iptables` que intercepta el puerto `8883` sin alterar la configuración de red de la Connect Box.
* `hassio_api: true` y `services: ["mqtt:want"]`: utilizados con rol estándar para obtener de forma segura la dirección y las credenciales del broker Mosquitto local.

---

## 8. Resolución de Problemas (Troubleshooting)

* **La Connect Box no se conecta (`Connessione Connect Box: Disconnesso`)**:
  1. Comprueba en los registros de Pi-hole / DNS local que la Connect Box esté resolviendo efectivamente `aldesiotsuite.azure-devices.net` hacia la IP local de Home Assistant.
  2. Verifica que el parámetro `box_ip` en las opciones del complemento coincida con la IP real de la Connect Box (o déjalo vacío para aceptar conexiones de toda la subred).
  3. Desconecta y vuelve a conectar la alimentación de la Connect Box para forzar una reconexión inmediata (la unidad realiza intentos con espera progresiva cuando pierde conexión con la nube).
* **Error `CONNACK rifiutato da Mosquitto (rc=4 o rc=5)` en los registros**:
  * Introduce manualmente un nombre de usuario y una contraseña válidos de Home Assistant / Mosquitto en los campos `ha_mqtt_user` y `ha_mqtt_password` de la pestaña Configuración del complemento y reinícialo.
