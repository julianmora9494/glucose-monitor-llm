"""
Importacion historica de glucosa -> DuckDB.

MODOS DE USO
============

1. Desde LibreLinkUp (requiere internet):
   python scripts/import_history.py

   Combina graph() (~12h continuo) + logbook() (~14 dias escaneos manuales).
   LIMITACION: la API de LibreLinkUp no expone el historial continuo completo.
   Para el historial completo usar el modo CSV (ver punto 3).

2. Solo recalcular resumenes desde lecturas ya en DuckDB (sin internet):
   python scripts/import_history.py --offline

3. Desde CSV exportado de LibreView (historial completo hasta 90 dias):
   python scripts/import_history.py --csv ruta/al/archivo.csv

   Como exportar el CSV:
   a) Entrar a https://www.libreview.com con las mismas credenciales
   b) Menu -> Mis datos -> Exportar datos (o "Download my data")
   c) Seleccionar rango maximo disponible
   d) Guardar el archivo .csv y pasarle la ruta a este script

   El CSV de LibreView tiene columnas como:
   'Sello de tiempo del dispositivo', 'Historial de glucosa mg/dL',
   'Escanear glucosa mg/dL', etc.
"""

import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Permitir ejecucion desde la raiz del proyecto o desde scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from api.services.db import (
    get_readings_by_date,
    initialize_schema,
    insert_reading,
    upsert_daily_summary,
)
from api.services.metrics import calculate_daily_metrics

# ─── Configuracion LibreLinkUp ────────────────────────────────────────────────
LIBRE_EMAIL    = os.getenv("LIBRE_EMAIL")
LIBRE_PASSWORD = os.getenv("LIBRE_PASSWORD")
LIBRE_REGION   = os.getenv("LIBRE_REGION", "LA").upper()

REGION_MAP: dict = {}
try:
    from pylibrelinkup import PyLibreLinkUp
    from pylibrelinkup.api_url import APIUrl
    REGION_MAP = {"LA": APIUrl.LA, "EU": APIUrl.EU, "US": APIUrl.US, "AP": APIUrl.AP}
except ImportError:
    pass


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _range_type(glucose: float) -> str:
    """Clasifica una lectura en su rango glucemico."""
    if glucose < 54:  return "very_low"
    if glucose < 70:  return "low"
    if glucose <= 180: return "normal"
    if glucose <= 250: return "high"
    return "very_high"


def _insert(ts: datetime, glucose: float, trend: Optional[str] = None) -> bool:
    """Inserta una lectura con deduplicacion. Retorna True si fue nueva."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return insert_reading(
        timestamp=ts,
        glucose_mgdl=glucose,
        trend=trend,
        delta_mgdl=None,
        dt_min=None,
        slope_mgdl_min=None,
        percent_change=None,
        range_type=_range_type(glucose),
    )


def _backfill_derived_metrics() -> None:
    """
    Calcula delta/slope/dt_min/percent_change para lecturas con estos campos NULL.
    Replica la logica del monitor: compara cada lectura con la anterior por timestamp.
    """
    import duckdb
    DATABASE_URL = os.getenv("DATABASE_URL", "data/glucose.duckdb")
    con = duckdb.connect(DATABASE_URL)

    rows = con.execute("""
        SELECT id, timestamp, glucose_mgdl
        FROM readings
        ORDER BY timestamp ASC
    """).fetchall()

    if len(rows) < 2:
        print("Menos de 2 lecturas — no se pueden calcular deltas.")
        con.close()
        return

    updated = 0
    for i in range(1, len(rows)):
        curr_id, curr_ts, curr_g = rows[i]
        prev_id, prev_ts, prev_g = rows[i - 1]

        # Solo actualizar lecturas con campos derivados NULL
        existing = con.execute(
            "SELECT delta_mgdl FROM readings WHERE id = ?", [curr_id]
        ).fetchone()
        if existing[0] is not None:
            continue

        dt_min = (curr_ts - prev_ts).total_seconds() / 60
        if dt_min <= 0 or dt_min > 15:
            # Saltos >15 min indican datos no consecutivos
            continue

        delta = curr_g - prev_g
        slope = delta / dt_min
        pct = (delta / prev_g) * 100 if prev_g != 0 else 0.0

        con.execute("""
            UPDATE readings
            SET delta_mgdl = ?, dt_min = ?, slope_mgdl_min = ?, percent_change = ?
            WHERE id = ?
        """, [delta, dt_min, slope, pct, curr_id])
        updated += 1

    con.close()
    print(f"Metricas derivadas calculadas: {updated} lecturas actualizadas")


def _recalculate_summaries(dates: set) -> None:
    """Calcula y persiste el resumen AGP para cada fecha del set."""
    if not dates:
        print("Sin fechas nuevas para calcular.")
        return
    print("Calculando resumenes diarios...")
    ok_days = 0
    for d in sorted(dates):
        df = get_readings_by_date(d)
        if len(df) >= 3:
            summary = calculate_daily_metrics(df)
            summary["date"] = d
            upsert_daily_summary(summary)
            tir = summary.get("tir_percent", 0)
            n   = summary.get("reading_count", 0)
            print(f"  {d}: {n:3d} lecturas | TIR {tir:.1f}%")
            ok_days += 1
        else:
            print(f"  {d}: {len(df):3d} lecturas (menos de 3, sin resumen)")
    print(f"Resumenes calculados: {ok_days} dias con datos suficientes")


def _recalculate_all_from_db() -> None:
    """Modo --offline: recalcula summaries desde lecturas ya en DuckDB."""
    import duckdb
    DATABASE_URL = os.getenv("DATABASE_URL", "data/glucose.duckdb")
    con = duckdb.connect(DATABASE_URL)
    rows = con.execute(
        "SELECT DISTINCT CAST(timestamp AT TIME ZONE 'America/Bogota' AS DATE) as d FROM readings ORDER BY d"
    ).fetchall()
    con.close()
    dates = {row[0] for row in rows}
    print(f"Dias con lecturas en DuckDB: {len(dates)}")
    _backfill_derived_metrics()
    _recalculate_summaries(dates)


# ─── Modo 1: LibreLinkUp (graph + logbook) ───────────────────────────────────

def _import_from_librelink() -> None:
    """Descarga datos de los dos endpoints disponibles y los combina."""
    if not LIBRE_EMAIL or not LIBRE_PASSWORD:
        print("[ERROR] Falta LIBRE_EMAIL o LIBRE_PASSWORD en el .env")
        sys.exit(1)
    if LIBRE_REGION not in REGION_MAP:
        print("[ERROR] LIBRE_REGION debe ser LA, EU, US o AP")
        sys.exit(1)

    print("Autenticando con LibreLinkUp...")
    try:
        client = PyLibreLinkUp(
            email=LIBRE_EMAIL,
            password=LIBRE_PASSWORD,
            api_url=REGION_MAP[LIBRE_REGION],
        )
        client.authenticate()
    except Exception as e:
        print(f"\n[ERROR de red] No se pudo conectar: {e}")
        print("\nOpciones:")
        print("  Sin internet  -> python scripts/import_history.py --offline")
        print("  CSV completo  -> python scripts/import_history.py --csv archivo.csv")
        sys.exit(1)

    patients = client.get_patients()
    if not patients:
        print("[ERROR] No hay pacientes vinculados.")
        sys.exit(1)

    patient = patients[0]
    nombre = f"{getattr(patient,'first_name','')} {getattr(patient,'last_name','')}".strip()
    print(f"Paciente: {nombre}\n")

    # Combinar graph() (~12h continuo) + logbook() (~14 dias de escaneos)
    all_measurements = []

    print("Descargando graph() — ultimas ~12 horas continuas...")
    try:
        graph_data = client.graph(patient)
        print(f"  {len(graph_data)} lecturas obtenidas")
        all_measurements.extend(graph_data)
    except Exception as e:
        print(f"  [WARN] graph() fallo: {e}")

    print("Descargando logbook() — historial de escaneos (~14 dias)...")
    try:
        logbook_data = client.logbook(patient)
        print(f"  {len(logbook_data)} lecturas obtenidas")
        all_measurements.extend(logbook_data)
    except Exception as e:
        print(f"  [WARN] logbook() fallo: {e}")

    print(f"\nTotal a procesar: {len(all_measurements)} lecturas (con posibles duplicados)\n")

    inserted = 0
    skipped  = 0
    dates_seen: set = set()

    for m in all_measurements:
        ts      = m.timestamp
        glucose = m.value_in_mg_per_dl
        if ts is None or glucose is None:
            skipped += 1
            continue
        trend = str(getattr(m, "trend", "") or "") or None
        if _insert(ts, float(glucose), trend):
            inserted += 1
            dates_seen.add(ts.date() if hasattr(ts, 'date') else ts)
        else:
            skipped += 1

    print(f"Lecturas nuevas   : {inserted}")
    print(f"Ya existian (skip): {skipped}")
    print(f"Dias afectados    : {len(dates_seen)}\n")

    print("NOTA: La API de LibreLinkUp solo expone ~12h continuas (graph)")
    print("y los escaneos manuales del sensor (logbook). Para el historial")
    print("completo de 14 dias exportar CSV desde https://www.libreview.com\n")

    _backfill_derived_metrics()
    _recalculate_summaries(dates_seen)


# ─── Modo 2: CSV de LibreView ─────────────────────────────────────────────────

# Posibles nombres de columna en el CSV de LibreView segun idioma/version
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

def _find_col(header: list[str], candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in header:
            return c
    return None

def _parse_libre_ts(raw: str) -> Optional[datetime]:
    """
    Parsea el timestamp del CSV de LibreView (varios formatos).
    LibreView exporta en hora LOCAL del dispositivo (Colombia = UTC-5).
    """
    # Colombia no tiene horario de verano → offset fijo -05:00
    _COL_TZ = timezone(timedelta(hours=-5))
    for fmt in ("%m/%d/%Y %I:%M %p", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=_COL_TZ)
        except ValueError:
            continue
    return None

def _import_from_csv(csv_path: str) -> None:
    """Importa lecturas desde el CSV exportado de LibreView."""
    path = Path(csv_path)
    if not path.exists():
        print(f"[ERROR] Archivo no encontrado: {csv_path}")
        sys.exit(1)

    print(f"Leyendo CSV: {path.name}")

    inserted = 0
    skipped  = 0
    errors   = 0
    dates_seen: set = set()

    with open(path, encoding="utf-8-sig", newline="") as f:
        # Saltar filas de cabecera del CSV de LibreView (primeras ~2 lineas de metadata)
        lines = f.readlines()

    # Encontrar la fila real de encabezados (la que tiene columnas de timestamp)
    header_row = 0
    for i, line in enumerate(lines):
        if any(c in line for c in _TS_COLS + ["Device Timestamp", "Sello", "Marca de hora"]):
            header_row = i
            break

    data_lines = lines[header_row:]
    reader = csv.DictReader(data_lines)
    header = reader.fieldnames or []

    ts_col   = _find_col(header, _TS_COLS)
    hist_col = _find_col(header, _HIST_COLS)
    scan_col = _find_col(header, _SCAN_COLS)

    if not ts_col:
        print("[ERROR] No se encontro columna de timestamp en el CSV.")
        print("Columnas disponibles: " + str(header))
        sys.exit(1)

    print(f"Columna timestamp : {ts_col}")
    print(f"Columna historico : {hist_col}")
    print(f"Columna escaneo   : {scan_col}")
    print()

    for row in reader:
        raw_ts = row.get(ts_col, "").strip()
        if not raw_ts:
            continue

        ts = _parse_libre_ts(raw_ts)
        if ts is None:
            errors += 1
            continue

        # Preferir historial continuo; si no, usar escaneo manual
        glucose_raw = ""
        if hist_col:
            glucose_raw = row.get(hist_col, "").strip()
        if not glucose_raw and scan_col:
            glucose_raw = row.get(scan_col, "").strip()
        if not glucose_raw:
            skipped += 1
            continue

        try:
            glucose = float(glucose_raw.replace(",", "."))
        except ValueError:
            errors += 1
            continue

        if _insert(ts, glucose):
            inserted += 1
            dates_seen.add(ts.date())
        else:
            skipped += 1

    print(f"Lecturas nuevas     : {inserted}")
    print(f"Ya existian (skip)  : {skipped}")
    print(f"Errores de formato  : {errors}")
    print(f"Dias afectados      : {len(dates_seen)}\n")

    _backfill_derived_metrics()
    _recalculate_summaries(dates_seen)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    print("=== Importacion historica -> DuckDB ===\n")
    initialize_schema()

    if "--offline" in args:
        print("Modo offline: recalculando summaries desde DuckDB...\n")
        _recalculate_all_from_db()
        print("\nListo.")
        return

    if "--csv" in args:
        idx = args.index("--csv")
        if idx + 1 >= len(args):
            print("[ERROR] Falta la ruta al CSV despues de --csv")
            print("Uso: python scripts/import_history.py --csv ruta/al/archivo.csv")
            sys.exit(1)
        csv_path = args[idx + 1]
        _import_from_csv(csv_path)
        print("\nImportacion CSV completada!")
        return

    # Modo por defecto: LibreLinkUp online
    _import_from_librelink()
    print("\nImportacion completada!")


if __name__ == "__main__":
    main()
