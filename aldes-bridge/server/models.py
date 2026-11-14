"""Definiciones estructuradas de los sensores y modos de funcionamiento de la VMC.

Este módulo sustituye las antiguas tuplas posicionales por objetos legibles.
Para desactivar un sensor en Home Assistant basta con establecer is_active=False.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SensorDefinition:
    """Representa la configuración técnica de un sensor individual de la VMC."""

    sensor_id: str                        # ID único utilizado en los topics de Home Assistant
    telemetry_key: str                    # Clave exacta presente en el JSON enviado por la Connect Box
    unit: Optional[str] = None            # Unidad de medida (p. ej. °C, m³/h, rpm)
    device_class: Optional[str] = None    # Clase de dispositivo de Home Assistant (p. ej. temperature, power)
    state_class: Optional[str] = None     # Clase estadística de HA (p. ej. measurement)
    icon: str = "mdi:gauge"               # Icono Material Design (mdi:...)
    enabled_by_default: bool = True       # Si es False, el sensor se crea pero permanece oculto por defecto
    value_type: str = "string"            # Formato del valor: "float", "int" o "string"
    is_active: bool = True                # Si es False, el sensor se elimina de Home Assistant


# Lista completa de sensores leídos del payload JSON de la Connect Box
TELEMETRY_SENSORS: list[SensorDefinition] = [
    # --- Temperaturas ---
    SensorDefinition(
        sensor_id="outside_tpt",
        telemetry_key="outside_tpt",
        unit="\u00b0C",
        device_class="temperature",
        state_class="measurement",
        icon="mdi:thermometer",
        value_type="float",
    ),
    SensorDefinition(
        sensor_id="ext_tpt",
        telemetry_key="ext_tpt",
        unit="\u00b0C",
        device_class="temperature",
        state_class="measurement",
        icon="mdi:home-thermometer",
        value_type="float",
    ),
    SensorDefinition(
        sensor_id="reject_tpt",
        telemetry_key="reject_tpt",
        unit="\u00b0C",
        device_class="temperature",
        state_class="measurement",
        icon="mdi:thermometer-chevron-down",
        value_type="float",
    ),

    # --- Caudales de aire y velocidad de ventiladores ---
    SensorDefinition(
        sensor_id="extf_flw",
        telemetry_key="extf_flw",
        unit="m\u00b3/h",
        state_class="measurement",
        icon="mdi:weather-windy",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="ffe_flw",
        telemetry_key="ffe_flw",
        unit="m\u00b3/h",
        state_class="measurement",
        icon="mdi:air-filter",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="extf_spd",
        telemetry_key="extf_spd",
        unit="rpm",
        state_class="measurement",
        icon="mdi:fan",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="vi_spd",
        telemetry_key="vi_spd",
        unit="rpm",
        state_class="measurement",
        icon="mdi:fan",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="set_spd",
        telemetry_key="set_spd",
        state_class="measurement",
        icon="mdi:speedometer",
        value_type="int",
    ),

    # --- Estado de funcionamiento y mantenimiento ---
    SensorDefinition(
        sensor_id="current_mode",
        telemetry_key="current_mode",
        icon="mdi:tune",
        value_type="string",
    ),
    SensorDefinition(
        sensor_id="ff_cpt",
        telemetry_key="ff_cpt",
        unit="%",
        state_class="measurement",
        icon="mdi:air-filter",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="dep_ind",
        telemetry_key="dep_ind",
        state_class="measurement",
        icon="mdi:gauge",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="dtb_ind",
        telemetry_key="dtb_ind",
        state_class="measurement",
        icon="mdi:valve",
        value_type="int",
    ),

    # --- Diagnóstico y Firmware ---
    # El sensor RSSI devuelve "--%%" fijo en la Connect Box: se mantiene en el código
    # con is_active=False para que se elimine automáticamente de Home Assistant.
    SensorDefinition(
        sensor_id="rssi",
        telemetry_key="RSSI",
        icon="mdi:wifi",
        enabled_by_default=False,
        value_type="string",
        is_active=False,
    ),
    SensorDefinition(
        sensor_id="vers_uc",
        telemetry_key="Vers_UC",
        icon="mdi:chip",
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="vers_w",
        telemetry_key="Vers_W",
        icon="mdi:wifi-cog",
        value_type="string",
    ),

    # --- Sensores opcionales (creados pero deshabilitados por defecto en Home Assistant) ---
    SensorDefinition(
        sensor_id="co2_vmc",
        telemetry_key="Co2_vmc",
        unit="ppm",
        device_class="carbon_dioxide",
        state_class="measurement",
        icon="mdi:molecule-co2",
        enabled_by_default=False,
        value_type="float",
    ),
    SensorDefinition(
        sensor_id="pm25_vmc",
        telemetry_key="Pm25_Vmc",
        unit="\u00b5g/m\u00b3",
        device_class="pm25",
        state_class="measurement",
        icon="mdi:blur",
        enabled_by_default=False,
        value_type="float",
    ),
    SensorDefinition(
        sensor_id="voc_vmc",
        telemetry_key="Voc_Vmc",
        unit="ppm",
        state_class="measurement",
        icon="mdi:chemical-weapon",
        enabled_by_default=False,
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="cve_csn",
        telemetry_key="cve_csn",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:flash",
        enabled_by_default=False,
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="vi_csn",
        telemetry_key="vi_csn",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:flash",
        enabled_by_default=False,
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="tte_csn",
        telemetry_key="tte_csn",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:flash",
        enabled_by_default=False,
        value_type="int",
    ),
    SensorDefinition(
        sensor_id="echange_pwr",
        telemetry_key="echange_pwr",
        unit="W",
        device_class="power",
        state_class="measurement",
        icon="mdi:heat-wave",
        enabled_by_default=False,
        value_type="int",
    ),
]
