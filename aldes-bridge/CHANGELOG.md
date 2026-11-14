# Registro de Cambios (Changelog)

Todos los cambios relevantes de **Aldes Bridge SC150** se documentan en este archivo.

## [2.2.2] - 2026-11-05

### Optimizado
- **Timeout TLS del socket**: aumentado el tiempo de espera de lectura del socket a **660 segundos (11 minutos)** dentro del gestor de sesión (`server/bridge.py`), eliminando de raíz las desconexiones periódicas por timeout causadas por los retrasos del módulo Wi-Fi HF-LPB100.

## [2.2.1] - 2026-11-05

### Añadido
- **Cambios gráficos**: añadidos icono y logotipo.

## [2.2.0] - 2026-11-05

### Añadido
- **Monitorización inteligente de filtros (`server/filters.py`)**: detección automática del reinicio de filtros realizado desde la pantalla de la VMC (`ff_cpt`), guardado persistente de la fecha de reinicio en `/config/aldes/filters.json` y exposición de 4 nuevos sensores dedicados (`Giorni Residui Filtro`, `Giorni Utilizzo Filtro`, `Usura Stimata Filtro`, `Ultimo Reset Filtro`).
- **Opción `filter_months`**: nuevo parámetro en la configuración del complemento para establecer la duración nominal de los filtros en meses (por defecto `6` meses = 180 días).
- **Filtro antidesconexión (Grace Timer 30s)**: eliminados los falsos estados `Desconectado` de 5 segundos causados por la renovación de sesión TLS que la Connect Box realiza cada 5 horas.

### Modificado
- **Arquitectura modular del código**: división del antiguo archivo monolítico en módulos especializados y documentados (`models.py`, `config.py`, `filters.py`, `discovery.py`, `bridge.py`, `main.py`) con variables estandarizadas en inglés.

## [2.1.3] - 2026-11-05

### Corregido
- **Modo Vacaciones (`W`)**: parámetro `changeMode` formateado como una única cadena concatenada (`W<inicio_UTC>Z<fin_UTC>Z`).
- **Normalización de saltos de línea LF**: garantizados los saltos de línea Unix en `run.sh` y `apparmor.txt`.
