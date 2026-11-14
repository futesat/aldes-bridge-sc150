"""Monitorización inteligente del desgaste de los filtros de la VMC.

La Connect Box envía el parámetro `ff_cpt` (0-100), que representa el avance
del desgaste del filtro. Cuando el usuario realiza el reinicio de los filtros desde la pantalla de la VMC,
`ff_cpt` vuelve a empezar desde 0.

Este módulo:
1. Reconoce automáticamente la puesta a cero de `ff_cpt` (o una caída de al menos FILTER_RESET_DROP puntos).
2. Guarda la fecha exacta del último reinicio en el archivo persistente `/config/aldes/filters.json`.
3. Si aún no existe una fecha de reinicio guardada (primer inicio), la estima hacia atrás a partir
   del valor actual de `ff_cpt` y de la duración configurada (`filter_months` * 30 días).
4. Calcula los días transcurridos, los días restantes y el porcentaje de desgaste.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .config import FILTER_STORAGE_PATH

_log = logging.getLogger("aldes-sc150")

DAYS_PER_FILTER_MONTH = 30
FILTER_RESET_DROP = 10.0


def is_filter_reset(previous_value: Optional[float], current_value: Optional[float]) -> bool:
    """Devuelve True si el contador ff_cpt se ha puesto a cero o ha bajado al menos 10 puntos."""
    if previous_value is None or current_value is None:
        return False
    if previous_value > 0 and current_value == 0:
        return True
    return (previous_value - current_value) >= FILTER_RESET_DROP


def estimate_last_reset(now: datetime, ff_cpt_value: float, duration_days: int) -> datetime:
    """Estima la fecha del último cambio de filtro según el porcentaje ff_cpt actual."""
    clamped_ff = max(0.0, min(100.0, float(ff_cpt_value)))
    elapsed_days = (clamped_ff / 100.0) * duration_days
    return now - timedelta(days=elapsed_days)


@dataclass
class FilterInfo:
    """Resumen calculado sobre el estado actual de los filtros de la VMC."""

    last_reset: datetime
    elapsed_days: int
    duration_days: int
    remaining_days: int
    wear_percent: float


class FilterTracker:
    """Gestiona el almacenamiento en disco y el cálculo de la vida útil restante de los filtros."""

    def __init__(self, filter_months: int = 6, storage_path: str = FILTER_STORAGE_PATH) -> None:
        self.filter_months = max(1, int(filter_months))
        self.storage_path = storage_path
        self.last_reset: Optional[datetime] = None
        self.last_ff_cpt: Optional[float] = None
        self.load_from_disk()

    @property
    def duration_days(self) -> int:
        """Duración total del filtro en días (p. ej. 6 meses * 30 = 180 días)."""
        return self.filter_months * DAYS_PER_FILTER_MONTH

    def load_from_disk(self) -> None:
        """Carga la fecha del último reinicio desde el archivo JSON persistente."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as file_handle:
                stored_data = json.load(file_handle)
            raw_date = stored_data.get("last_reset")
            if raw_date:
                parsed_date = datetime.fromisoformat(raw_date)
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                self.last_reset = parsed_date
            raw_ff = stored_data.get("last_ff")
            if isinstance(raw_ff, (int, float)):
                self.last_ff_cpt = float(raw_ff)
        except FileNotFoundError:
            pass
        except Exception as exc:
            _log.warning("Impossibile leggere lo stato filtri da %s: %s", self.storage_path, exc)

    def save_to_disk(self) -> None:
        """Guarda de forma atómica la fecha del último reinicio y el último valor ff_cpt."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            temp_path = self.storage_path + ".tmp"
            payload = {
                "last_reset": self.last_reset.isoformat() if self.last_reset else None,
                "last_ff": self.last_ff_cpt,
            }
            with open(temp_path, "w", encoding="utf-8") as file_handle:
                json.dump(payload, file_handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.storage_path)
        except Exception as exc:
            _log.warning("Impossibile salvare lo stato filtri in %s: %s", self.storage_path, exc)

    def update_from_telemetry(self, raw_ff_cpt: Any, now: Optional[datetime] = None) -> Optional[FilterInfo]:
        """Actualiza el estado del filtro cuando llega un nuevo paquete desde la Connect Box."""
        if raw_ff_cpt is None:
            return self.get_info(now=now)
        try:
            current_ff = float(raw_ff_cpt)
        except (ValueError, TypeError):
            return self.get_info(now=now)

        current_time = now or datetime.now(timezone.utc)

        if self.last_reset is None:
            # Primer inicio absoluto: se estima la fecha de inicio partiendo de ff_cpt
            self.last_reset = estimate_last_reset(current_time, current_ff, self.duration_days)
            self.last_ff_cpt = current_ff
            _log.info(
                "Primo avvio tracker filtri: ultimo reset stimato al %s (da ff_cpt=%s%%)",
                self.last_reset.strftime("%Y-%m-%d"),
                current_ff,
            )
            self.save_to_disk()
        elif is_filter_reset(self.last_ff_cpt, current_ff):
            # Detectada puesta a cero desde la pantalla de la VMC
            _log.info("Reset filtri rilevato! (ff_cpt passato da %s a %s)", self.last_ff_cpt, current_ff)
            self.last_reset = current_time
            self.last_ff_cpt = current_ff
            self.save_to_disk()
        elif current_ff != self.last_ff_cpt:
            self.last_ff_cpt = current_ff
            self.save_to_disk()

        return self.get_info(now=current_time)

    def get_info(self, now: Optional[datetime] = None) -> Optional[FilterInfo]:
        """Calcula y devuelve los días transcurridos, los días restantes y el porcentaje de desgaste."""
        if self.last_reset is None:
            return None
        current_time = now or datetime.now(timezone.utc)
        total_duration = self.duration_days
        elapsed_days_float = max(0.0, (current_time - self.last_reset).total_seconds() / 86400.0)
        elapsed_days_int = int(elapsed_days_float)
        remaining_days = max(0, total_duration - elapsed_days_int)
        wear_percent = round(min(100.0, (elapsed_days_float / total_duration) * 100.0), 1)

        return FilterInfo(
            last_reset=self.last_reset,
            elapsed_days=elapsed_days_int,
            duration_days=total_duration,
            remaining_days=remaining_days,
            wear_percent=wear_percent,
        )
