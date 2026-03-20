"""
Servicio de base de datos DuckDB.
Maneja el schema, conexión y operaciones de lectura/escritura de glucosa.
"""

import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "data/glucose.duckdb")


def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """
    Retorna una conexión al archivo DuckDB.
    Por defecto read_only=True para no bloquear las escrituras del monitor.
    Usar read_only=False solo para operaciones de escritura (upsert_daily_summary).
    """
    Path(DATABASE_URL).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(DATABASE_URL, read_only=read_only)


def initialize_schema() -> None:
    """Crea las tablas si no existen. Idempotente."""
    con = get_connection(read_only=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id              INTEGER PRIMARY KEY,
            timestamp       TIMESTAMPTZ NOT NULL,
            glucose_mgdl    DOUBLE NOT NULL,
            trend           VARCHAR,
            delta_mgdl      DOUBLE,
            dt_min          DOUBLE,
            slope_mgdl_min  DOUBLE,
            percent_change  DOUBLE,
            range_type      VARCHAR
        )
    """)
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS readings_id_seq START 1
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            date                DATE PRIMARY KEY,
            reading_count       INTEGER,
            avg_glucose         DOUBLE,
            std_glucose         DOUBLE,
            cv_percent          DOUBLE,
            tir_percent         DOUBLE,
            tar_percent         DOUBLE,
            tbr_percent         DOUBLE,
            tbr_severe_percent  DOUBLE,
            gmi_percent         DOUBLE,
            mage_mgdl           DOUBLE,
            hypo_episodes       INTEGER,
            hyper_episodes      INTEGER,
            min_glucose         DOUBLE,
            max_glucose         DOUBLE,
            llm_summary         TEXT
        )
    """)
    con.close()


def insert_reading(
    timestamp: datetime,
    glucose_mgdl: float,
    trend: Optional[str],
    delta_mgdl: Optional[float],
    dt_min: Optional[float],
    slope_mgdl_min: Optional[float],
    percent_change: Optional[float],
    range_type: str,
) -> bool:
    """
    Inserta una lectura nueva. Retorna True si se insertó, False si ya existía
    (deduplicación por timestamp exacto).
    """
    con = get_connection(read_only=False)
    try:
        existing = con.execute(
            "SELECT COUNT(*) FROM readings WHERE timestamp = ?",
            [timestamp]
        ).fetchone()[0]

        if existing > 0:
            return False

        next_id = con.execute("SELECT nextval('readings_id_seq')").fetchone()[0]
        con.execute("""
            INSERT INTO readings
                (id, timestamp, glucose_mgdl, trend, delta_mgdl, dt_min,
                 slope_mgdl_min, percent_change, range_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [next_id, timestamp, glucose_mgdl, trend, delta_mgdl, dt_min,
              slope_mgdl_min, percent_change, range_type])
        return True
    finally:
        con.close()


def get_readings_by_date(target_date: date) -> pd.DataFrame:
    """Retorna todas las lecturas de un día como DataFrame."""
    con = get_connection()
    try:
        df = con.execute("""
            SELECT timestamp, glucose_mgdl, trend, delta_mgdl,
                   dt_min, slope_mgdl_min, percent_change, range_type
            FROM readings
            WHERE CAST(timestamp AS DATE) = ?
            ORDER BY timestamp ASC
        """, [target_date]).df()
        return df
    finally:
        con.close()


def get_readings_last_hours(hours: int = 3) -> pd.DataFrame:
    """Retorna las lecturas de las últimas N horas."""
    con = get_connection()
    try:
        interval = f"{hours} hours"
        df = con.execute("""
            SELECT timestamp, glucose_mgdl, trend, delta_mgdl,
                   slope_mgdl_min, range_type
            FROM readings
            WHERE timestamp >= now() - INTERVAL ?
            ORDER BY timestamp ASC
        """, [interval]).df()
        return df
    finally:
        con.close()


def get_latest_reading() -> Optional[dict]:
    """Retorna la lectura más reciente como diccionario."""
    con = get_connection()
    try:
        row = con.execute("""
            SELECT timestamp, glucose_mgdl, trend, delta_mgdl,
                   slope_mgdl_min, range_type
            FROM readings
            ORDER BY timestamp DESC
            LIMIT 1
        """).fetchone()
        if not row:
            return None
        return {
            "timestamp": row[0],
            "glucose_mgdl": row[1],
            "trend": row[2],
            "delta_mgdl": row[3],
            "slope_mgdl_min": row[4],
            "range_type": row[5],
        }
    finally:
        con.close()


def upsert_daily_summary(summary: dict) -> None:
    """Inserta o actualiza el resumen del día."""
    con = get_connection(read_only=False)
    try:
        con.execute("""
            INSERT OR REPLACE INTO daily_summaries VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, [
            summary["date"],
            summary["reading_count"],
            summary["avg_glucose"],
            summary["std_glucose"],
            summary["cv_percent"],
            summary["tir_percent"],
            summary["tar_percent"],
            summary["tbr_percent"],
            summary["tbr_severe_percent"],
            summary["gmi_percent"],
            summary["mage_mgdl"],
            summary["hypo_episodes"],
            summary["hyper_episodes"],
            summary["min_glucose"],
            summary["max_glucose"],
            summary.get("llm_summary"),
        ])
    finally:
        con.close()


def get_daily_summaries(days: int = 7) -> pd.DataFrame:
    """Retorna los últimos N días de resúmenes clínicos."""
    con = get_connection()
    try:
        df = con.execute("""
            SELECT * FROM daily_summaries
            ORDER BY date DESC
            LIMIT ?
        """, [days]).df()
        return df
    finally:
        con.close()


def migrate_from_csv(csv_dir: str = "data") -> int:
    """
    Migra datos históricos de los archivos CSV diarios a DuckDB.
    Retorna el número de lecturas insertadas.
    """
    import glob

    initialize_schema()
    csv_files = glob.glob(f"{csv_dir}/glucose_*.csv")
    total_inserted = 0

    for csv_path in sorted(csv_files):
        try:
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                ts = pd.to_datetime(row["timestamp"])
                inserted = insert_reading(
                    timestamp=ts,
                    glucose_mgdl=float(row["glucose_mgdl"]),
                    trend=str(row.get("trend", "")) or None,
                    delta_mgdl=float(row["delta_mgdl"]) if pd.notna(row.get("delta_mgdl")) else None,
                    dt_min=float(row["dt_min"]) if pd.notna(row.get("dt_min")) else None,
                    slope_mgdl_min=float(row["slope_mgdl_min"]) if pd.notna(row.get("slope_mgdl_min")) else None,
                    percent_change=float(row["percent_change"]) if pd.notna(row.get("percent_change")) else None,
                    range_type=str(row.get("range_type", "normal")),
                )
                if inserted:
                    total_inserted += 1
        except Exception as e:
            print(f"[WARN] Error procesando {csv_path}: {e}")

    return total_inserted
