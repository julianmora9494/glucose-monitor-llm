"""
Importación histórica desde LibreLinkUp (logbook — ~14 días).

Uso:
    python scripts/import_history.py

El script se autentica con las credenciales del .env, descarga el logbook
completo del sensor (hasta ~14 días atrás) y lo inserta en DuckDB con
deduplicación por timestamp, igual que hace el monitor en cada lectura.
Al final calcula y guarda el resumen diario para cada día importado.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permitir ejecución desde la raíz del proyecto o desde scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl

load_dotenv()

from api.services.db import initialize_schema, insert_reading, get_readings_by_date
from api.services.metrics import calculate_daily_metrics
from api.services.db import upsert_daily_summary

# ─── Configuración ───────────────────────────────────────────────────────────
LIBRE_EMAIL    = os.getenv("LIBRE_EMAIL")
LIBRE_PASSWORD = os.getenv("LIBRE_PASSWORD")
LIBRE_REGION   = os.getenv("LIBRE_REGION", "LA").upper()

REGION_MAP = {
    "LA": APIUrl.LA,
    "EU": APIUrl.EU,
    "US": APIUrl.US,
    "AP": APIUrl.AP,
}

if not LIBRE_EMAIL or not LIBRE_PASSWORD:
    print("[ERROR] Falta LIBRE_EMAIL o LIBRE_PASSWORD en el .env")
    sys.exit(1)

if LIBRE_REGION not in REGION_MAP:
    print(f"[ERROR] LIBRE_REGION debe ser una de: {list(REGION_MAP)}")
    sys.exit(1)


def _range_type(glucose: float) -> str:
    """Clasifica la lectura en el rango glucémico."""
    if glucose < 54:
        return "very_low"
    if glucose < 70:
        return "low"
    if glucose <= 180:
        return "normal"
    if glucose <= 250:
        return "high"
    return "very_high"


def main() -> None:
    print("=== Importación histórica LibreLinkUp → DuckDB ===\n")

    # Inicializar base de datos
    initialize_schema()

    # Autenticar
    print("Autenticando con LibreLinkUp...")
    client = PyLibreLinkUp(
        email=LIBRE_EMAIL,
        password=LIBRE_PASSWORD,
        api_url=REGION_MAP[LIBRE_REGION],
    )
    client.authenticate()

    # Obtener paciente
    patients = client.get_patients()
    if not patients:
        print("[ERROR] No se encontraron pacientes vinculados.")
        sys.exit(1)

    patient = patients[0]
    print(f"Paciente: {getattr(patient, 'first_name', '')} {getattr(patient, 'last_name', '')}\n")

    # Descargar logbook (~14 días)
    print("Descargando logbook (hasta ~14 días)...")
    measurements = client.logbook(patient)
    print(f"  → {len(measurements)} lecturas descargadas del sensor\n")

    # Insertar lecturas en DuckDB
    inserted = 0
    skipped  = 0
    dates_seen: set = set()

    for m in measurements:
        ts       = m.timestamp
        glucose  = m.value_in_mg_per_dl

        if ts is None or glucose is None:
            skipped += 1
            continue

        # Normalizar a UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        trend = str(getattr(m, "trend", "") or "")

        ok = insert_reading(
            timestamp=ts,
            glucose_mgdl=float(glucose),
            trend=trend or None,
            delta_mgdl=None,
            dt_min=None,
            slope_mgdl_min=None,
            percent_change=None,
            range_type=_range_type(float(glucose)),
        )

        if ok:
            inserted += 1
            dates_seen.add(ts.date())
        else:
            skipped += 1

    print(f"Lecturas insertadas : {inserted}")
    print(f"Ya existían (skip)  : {skipped}")
    print(f"Días nuevos         : {len(dates_seen)}\n")

    # Recalcular resúmenes diarios para cada día importado
    if dates_seen:
        print("Calculando resúmenes diarios...")
        for d in sorted(dates_seen):
            df = get_readings_by_date(d)
            if len(df) >= 3:
                summary = calculate_daily_metrics(df)
                summary["date"] = d           # requerido por upsert_daily_summary
                upsert_daily_summary(summary)
                tir = summary.get("tir_percent", 0)
                n   = summary.get("reading_count", 0)
                print(f"  {d}  →  {n} lecturas  |  TIR {tir:.1f}%")
            else:
                print(f"  {d}  →  {len(df)} lecturas (insuficientes para resumen)")

    print("\n¡Importación completada!")


if __name__ == "__main__":
    main()
