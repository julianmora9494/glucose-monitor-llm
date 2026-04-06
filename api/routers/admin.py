"""
Router: administración e importación de datos desde CSVs de LibreView.
Solo la API toca DuckDB — este endpoint permite re-importar en caliente sin reiniciar.
"""

import csv
import os
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.services.db import get_readings_by_date, insert_reading, upsert_daily_summary
from api.services.metrics import calculate_daily_metrics

router = APIRouter()

# ─── Columnas del CSV de LibreView (varios idiomas) ───────────────────────────

_TS_COLS = [
    "Sello de tiempo del dispositivo",
    "Marca de hora del dispositivo",
    "Device Timestamp",
    "Gerätezeitstempel",
]
_HIST_COLS = [
    "Historial de glucosa mg/dL",
    "Historic Glucose mg/dL",
    "Historische Glukose mg/dL",
]
_SCAN_COLS = [
    "Escanear glucosa mg/dL",
    "Scan Glucose mg/dL",
    "Gescannte Glukose mg/dL",
]


def _range_type(glucose: float) -> str:
    if glucose < 54:   return "very_low"
    if glucose < 70:   return "low"
    if glucose <= 180: return "normal"
    if glucose <= 250: return "high"
    return "very_high"


def _find_col(header: list[str], candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in header:
            return c
    return None


def _parse_ts(raw: str) -> Optional[datetime]:
    """Parsea timestamp del CSV de LibreView. Colombia = UTC-5, sin horario de verano."""
    _COL_TZ = timezone(timedelta(hours=-5))
    for fmt in ("%m/%d/%Y %I:%M %p", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=_COL_TZ)
        except ValueError:
            continue
    return None


def _import_csv_file(csv_path: Path) -> dict:
    """
    Importa un archivo CSV de LibreView a DuckDB.
    Retorna dict con estadísticas de la importación.
    """
    inserted = 0
    skipped = 0
    errors = 0
    dates_seen: set[date] = set()

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()

    # Encontrar la fila de encabezados reales (ignorar metadata de LibreView)
    header_row = 0
    for i, line in enumerate(lines):
        if any(c in line for c in _TS_COLS + ["Device Timestamp", "Sello", "Marca de hora"]):
            header_row = i
            break

    reader = csv.DictReader(lines[header_row:])
    header = reader.fieldnames or []

    ts_col   = _find_col(header, _TS_COLS)
    hist_col = _find_col(header, _HIST_COLS)
    scan_col = _find_col(header, _SCAN_COLS)

    if not ts_col:
        raise ValueError(f"No se encontró columna de timestamp. Columnas: {header}")

    for row in reader:
        raw_ts = row.get(ts_col, "").strip()
        if not raw_ts:
            continue

        ts = _parse_ts(raw_ts)
        if ts is None:
            errors += 1
            continue

        # Preferir historial continuo (tipo 0); si no, usar escaneo manual
        glucose_raw = ""
        if hist_col:
            glucose_raw = row.get(hist_col, "").strip()
        if not glucose_raw and scan_col:
            glucose_raw = row.get(scan_col, "").strip()
        if not glucose_raw:
            # Fila sin glucosa (eventos, alarmas, notas — tipo 6 en LibreView)
            skipped += 1
            continue

        try:
            glucose = float(glucose_raw.replace(",", "."))
        except ValueError:
            errors += 1
            continue

        ok = insert_reading(
            timestamp=ts,
            glucose_mgdl=glucose,
            trend=None,
            delta_mgdl=None,
            dt_min=None,
            slope_mgdl_min=None,
            percent_change=None,
            range_type=_range_type(glucose),
        )
        if ok:
            inserted += 1
            dates_seen.add(ts.date())
        else:
            skipped += 1

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "dates": sorted(str(d) for d in dates_seen),
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/import-csv")
def import_csv_files() -> dict:
    """
    Escanea Examenes_resultados/ e importa todos los CSVs de LibreView encontrados.
    Seguro de ejecutar con la API corriendo — FastAPI es el único que escribe en DuckDB.
    Recalcula los resúmenes AGP de todas las fechas con datos nuevos.
    """
    csv_dir = Path(os.getenv("EXAMENES_DIR", "Examenes_resultados"))
    if not csv_dir.exists():
        raise HTTPException(status_code=404, detail=f"Directorio no encontrado: {csv_dir}")

    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        return {"message": "No se encontraron archivos CSV", "files_processed": 0, "total_inserted": 0}

    results = []
    all_dates: set[str] = set()
    total_inserted = 0

    for f in csv_files:
        try:
            stats = _import_csv_file(f)
            results.append({"file": f.name, **stats})
            total_inserted += stats["inserted"]
            all_dates.update(stats["dates"])
        except Exception as e:
            results.append({"file": f.name, "error": str(e), "inserted": 0})

    # Recalcular resúmenes AGP para todas las fechas con lecturas nuevas
    recalculated = []
    for date_str in sorted(all_dates):
        d = date.fromisoformat(date_str)
        df = get_readings_by_date(d)
        if len(df) >= 3:
            summary = calculate_daily_metrics(df)
            if summary:
                summary["date"] = d
                upsert_daily_summary(summary)
                recalculated.append(date_str)

    return {
        "total_inserted": total_inserted,
        "files_processed": len(csv_files),
        "files": results,
        "dates_recalculated": recalculated,
    }


@router.get("/db-status")
def db_status() -> dict:
    """Muestra el estado actual de la base de datos: total de lecturas, rango de fechas."""
    from api.services.db import get_connection
    con = get_connection()
    try:
        row = con.execute("""
            SELECT
                COUNT(*) as total,
                MIN(timestamp AT TIME ZONE 'America/Bogota') as primera,
                MAX(timestamp AT TIME ZONE 'America/Bogota') as ultima
            FROM readings
        """).fetchone()
    finally:
        con.close()

    if not row or row[0] == 0:
        return {"total_readings": 0, "primera_lectura": None, "ultima_lectura": None}

    return {
        "total_readings": row[0],
        "primera_lectura": str(row[1]),
        "ultima_lectura": str(row[2]),
    }
