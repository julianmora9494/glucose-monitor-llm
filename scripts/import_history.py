"""
Importación histórica desde LibreLinkUp (logbook — ~14 días).

Uso:
    python scripts/import_history.py            # Importa del sensor + calcula summaries
    python scripts/import_history.py --offline  # Solo recalcula summaries desde DuckDB

El modo --offline es útil cuando no hay conexión a internet o cuando el sensor
no está disponible pero ya existen lecturas en la base de datos.
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


def _recalculate_summaries(dates: set) -> None:
    """Calcula y persiste el resumen AGP para cada fecha del set."""
    if not dates:
        return
    print("Calculando resumenes diarios...")
    for d in sorted(dates):
        df = get_readings_by_date(d)
        if len(df) >= 3:
            summary = calculate_daily_metrics(df)
            summary["date"] = d
            upsert_daily_summary(summary)
            tir = summary.get("tir_percent", 0)
            n   = summary.get("reading_count", 0)
            print(f"  {d}: {n} lecturas | TIR {tir:.1f}%")
        else:
            print(f"  {d}: {len(df)} lecturas (insuficientes para resumen)")


def _recalculate_all_from_db() -> None:
    """Modo offline: recalcula summaries desde las lecturas ya en DuckDB."""
    import duckdb
    DATABASE_URL = os.getenv("DATABASE_URL", "data/glucose.duckdb")
    con = duckdb.connect(DATABASE_URL)
    rows = con.execute(
        "SELECT DISTINCT CAST(timestamp AS DATE) as d FROM readings ORDER BY d"
    ).fetchall()
    con.close()

    dates = {row[0] for row in rows}
    print(f"Dias encontrados en DuckDB: {len(dates)}")
    _recalculate_summaries(dates)


def main() -> None:
    offline = "--offline" in sys.argv

    print("=== Importacion historica LibreLinkUp -> DuckDB ===\n")
    initialize_schema()

    if offline:
        print("Modo offline: recalculando summaries desde lecturas existentes...\n")
        _recalculate_all_from_db()
        print("\nSummaries recalculados OK")
        return

    # ─── Modo online: descargar del sensor ───────────────────────────────────
    print("Autenticando con LibreLinkUp...")
    try:
        client = PyLibreLinkUp(
            email=LIBRE_EMAIL,
            password=LIBRE_PASSWORD,
            api_url=REGION_MAP[LIBRE_REGION],
        )
        client.authenticate()
    except Exception as e:
        print(f"\n[ERROR de red] No se pudo conectar a LibreLinkUp: {e}")
        print()
        print("Opciones:")
        print("  1. Verificar conexion a internet y volver a intentar.")
        print("  2. Si ya tienes lecturas en DuckDB, usar modo offline:")
        print("     python scripts/import_history.py --offline")
        sys.exit(1)

    patients = client.get_patients()
    if not patients:
        print("[ERROR] No se encontraron pacientes vinculados.")
        sys.exit(1)

    patient = patients[0]
    nombre = f"{getattr(patient, 'first_name', '')} {getattr(patient, 'last_name', '')}".strip()
    print(f"Paciente: {nombre}\n")

    print("Descargando logbook (hasta ~14 dias)...")
    measurements = client.logbook(patient)
    print(f"  {len(measurements)} lecturas descargadas del sensor\n")

    inserted = 0
    skipped  = 0
    dates_seen: set = set()

    for m in measurements:
        ts      = m.timestamp
        glucose = m.value_in_mg_per_dl

        if ts is None or glucose is None:
            skipped += 1
            continue

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
    print(f"Ya existian (skip)  : {skipped}")
    print(f"Dias nuevos         : {len(dates_seen)}\n")

    _recalculate_summaries(dates_seen)
    print("\nImportacion completada!")


if __name__ == "__main__":
    main()
