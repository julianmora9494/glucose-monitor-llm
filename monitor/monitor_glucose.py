import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb
import matplotlib
matplotlib.use("Agg")  # Sin GUI — compatible con ejecución en background
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import requests
from dotenv import load_dotenv
from pylibrelinkup import PyLibreLinkUp
from pylibrelinkup.api_url import APIUrl
from pylibrelinkup.exceptions import LLUAPIRateLimitError

load_dotenv()

# =========================================================
# Archivos locales
# =========================================================
STATE_FILE = Path("glucose_state.json")
DATA_DIR = Path("data")
CHART_DIR = Path("charts")
LOG_FILE = Path("glucose_monitor.log")

DATA_DIR.mkdir(exist_ok=True)
CHART_DIR.mkdir(exist_ok=True)

# =========================================================
# Logging
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("glucose-monitor")

# =========================================================
# Utilidades env
# =========================================================
def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


# =========================================================
# Configuración
# =========================================================
LIBRE_EMAIL = os.getenv("LIBRE_EMAIL")
LIBRE_PASSWORD = os.getenv("LIBRE_PASSWORD")
LIBRE_REGION = os.getenv("LIBRE_REGION", "LA").upper()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

POLL_SECONDS = env_int("POLL_SECONDS", 120)

LOW_THRESHOLD = env_float("LOW_THRESHOLD", 70)
VERY_LOW_THRESHOLD = env_float("VERY_LOW_THRESHOLD", 55)
HIGH_THRESHOLD = env_float("HIGH_THRESHOLD", 180)
VERY_HIGH_THRESHOLD = env_float("VERY_HIGH_THRESHOLD", 250)

RAPID_DROP_MGDL_MIN = env_float("RAPID_DROP_MGDL_MIN", -2.0)
RAPID_RISE_MGDL_MIN = env_float("RAPID_RISE_MGDL_MIN", 2.0)
EXTREME_DROP_MGDL_MIN = env_float("EXTREME_DROP_MGDL_MIN", -3.0)
EXTREME_RISE_MGDL_MIN = env_float("EXTREME_RISE_MGDL_MIN", 3.0)

RAPID_DROP_PERCENT = env_float("RAPID_DROP_PERCENT", -12.0)
RAPID_RISE_PERCENT = env_float("RAPID_RISE_PERCENT", 12.0)

PERSISTENCE_MINUTES = env_int("PERSISTENCE_MINUTES", 20)
NO_DATA_ALERT_MINUTES = env_int("NO_DATA_ALERT_MINUTES", 15)
COOLDOWN_MINUTES = env_int("COOLDOWN_MINUTES", 20)

SHOW_PLOT = os.getenv("SHOW_PLOT", "0") == "1"
SAVE_PLOT = os.getenv("SAVE_PLOT", "1") == "1"
DATABASE_URL = os.getenv("DATABASE_URL", "data/glucose.duckdb")

if not LIBRE_EMAIL or not LIBRE_PASSWORD:
    raise ValueError("Faltan LIBRE_EMAIL y/o LIBRE_PASSWORD en .env")

REGION_MAP = {
    "LA": APIUrl.LA,
    "EU": APIUrl.EU,
    "US": APIUrl.US,
    "AP": APIUrl.AP,
}

if LIBRE_REGION not in REGION_MAP:
    raise ValueError("LIBRE_REGION debe ser una de: LA, EU, US, AP")

client = PyLibreLinkUp(
    email=LIBRE_EMAIL,
    password=LIBRE_PASSWORD,
    api_url=REGION_MAP[LIBRE_REGION],
)

# =========================================================
# DuckDB — persistencia
# =========================================================
def _db_conn() -> duckdb.DuckDBPyConnection:
    """Retorna una conexión al archivo DuckDB."""
    Path(DATABASE_URL).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(DATABASE_URL)


def init_db() -> None:
    """Crea tablas si no existen. Idempotente."""
    con = _db_conn()
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
    con.execute("CREATE SEQUENCE IF NOT EXISTS readings_id_seq START 1")
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


def db_insert_reading(
    timestamp: datetime,
    glucose_mgdl: float,
    trend: Optional[str],
    delta_mgdl: Optional[float],
    dt_min: Optional[float],
    slope_mgdl_min: Optional[float],
    percent_change: Optional[float],
    range_type: str,
) -> bool:
    """Inserta lectura en DuckDB. Retorna False si ya existe (por timestamp)."""
    con = _db_conn()
    try:
        exists = con.execute(
            "SELECT COUNT(*) FROM readings WHERE timestamp = ?", [timestamp]
        ).fetchone()[0]
        if exists > 0:
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


def db_get_day(target_date: date) -> pd.DataFrame:
    """Retorna todas las lecturas de un día como DataFrame."""
    con = _db_conn()
    try:
        return con.execute("""
            SELECT timestamp, glucose_mgdl, trend, delta_mgdl,
                   dt_min, slope_mgdl_min, percent_change, range_type
            FROM readings
            WHERE CAST(timestamp AS DATE) = ?
            ORDER BY timestamp ASC
        """, [target_date]).df()
    finally:
        con.close()


def db_upsert_summary(summary: dict) -> None:
    """Guarda o actualiza el resumen diario."""
    con = _db_conn()
    try:
        con.execute("""
            INSERT OR REPLACE INTO daily_summaries VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, [
            summary["date"], summary["reading_count"],
            summary["avg_glucose"], summary["std_glucose"],
            summary["cv_percent"], summary["tir_percent"],
            summary["tar_percent"], summary["tbr_percent"],
            summary["tbr_severe_percent"], summary["gmi_percent"],
            summary.get("mage_mgdl"), summary["hypo_episodes"],
            summary["hyper_episodes"], summary["min_glucose"],
            summary["max_glucose"], summary.get("llm_summary"),
        ])
    finally:
        con.close()


def migrate_csv_to_db() -> int:
    """Migra los CSVs históricos a DuckDB al arrancar. Retorna lecturas insertadas."""
    import glob
    csv_files = glob.glob(str(DATA_DIR / "glucose_*.csv"))
    total = 0
    for csv_path in sorted(csv_files):
        try:
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                ts = pd.to_datetime(row["timestamp"])
                inserted = db_insert_reading(
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
                    total += 1
        except Exception as exc:
            logger.warning("Error migrando CSV %s: %s", csv_path, exc)
    return total


# =========================================================
# Métricas AGP
# =========================================================
def _calc_tir(g: pd.Series) -> float:
    return float(g.between(LOW_THRESHOLD, HIGH_THRESHOLD).mean() * 100) if len(g) else 0.0


def _calc_gmi(mean_g: float) -> float:
    """Glucose Management Indicator — estima HbA1c (ADA 2018)."""
    return round(3.31 + 0.02392 * mean_g, 2)


def _count_episodes(g: pd.Series, ts: pd.Series, threshold: float, above: bool) -> int:
    """Cuenta episodios de hipo o hiperglucemia (separados por ≥15 min sin evento)."""
    df = pd.DataFrame({"g": g.values, "ts": pd.to_datetime(ts.values)}).sort_values("ts").reset_index(drop=True)
    mask = df["g"] > threshold if above else df["g"] < threshold
    episodes, in_ep, last_ts = 0, False, None
    for i, row in df.iterrows():
        if mask[i]:
            if not in_ep:
                episodes += 1
                in_ep = True
            last_ts = row["ts"]
        elif in_ep and last_ts is not None:
            if (row["ts"] - last_ts).total_seconds() / 60 >= 15:
                in_ep = False
    return episodes


def calculate_agp_metrics(df: pd.DataFrame) -> dict:
    """Calcula métricas AGP completas para un DataFrame de lecturas."""
    if df.empty or len(df) < 3:
        return {}
    g = df["glucose_mgdl"]
    mean_g = float(g.mean())
    std_g = float(g.std()) if len(g) > 1 else 0.0
    cv = (std_g / mean_g * 100) if mean_g > 0 else 0.0
    return {
        "reading_count": len(g),
        "avg_glucose": round(mean_g, 1),
        "std_glucose": round(std_g, 1),
        "cv_percent": round(cv, 1),
        "tir_percent": round(_calc_tir(g), 1),
        "tar_percent": round(float((g > HIGH_THRESHOLD).mean() * 100), 1),
        "tbr_percent": round(float((g < LOW_THRESHOLD).mean() * 100), 1),
        "tbr_severe_percent": round(float((g < VERY_LOW_THRESHOLD).mean() * 100), 1),
        "gmi_percent": _calc_gmi(mean_g),
        "mage_mgdl": None,  # calculado con módulo completo en api/services/metrics.py
        "hypo_episodes": _count_episodes(g, df["timestamp"], LOW_THRESHOLD, above=False),
        "hyper_episodes": _count_episodes(g, df["timestamp"], HIGH_THRESHOLD, above=True),
        "min_glucose": float(g.min()),
        "max_glucose": float(g.max()),
    }


def _status_icon(value: float, ok_max: float, warn_max: float, higher_is_worse: bool = True) -> str:
    """Retorna ✅ ⚠️ 🔴 según el valor vs umbrales."""
    if higher_is_worse:
        if value <= ok_max:
            return "✅"
        if value <= warn_max:
            return "⚠️"
        return "🔴"
    else:
        if value >= ok_max:
            return "✅"
        if value >= warn_max:
            return "⚠️"
        return "🔴"


def format_daily_summary_telegram(metrics: dict, target_date: date) -> str:
    """Formatea el resumen diario AGP para Telegram con Markdown."""
    if not metrics:
        return f"Sin datos suficientes para {target_date}"

    tir_icon = _status_icon(metrics["tir_percent"], ok_max=70, warn_max=50, higher_is_worse=False)
    tar_icon = _status_icon(metrics["tar_percent"], ok_max=25, warn_max=40, higher_is_worse=True)
    tbr_icon = _status_icon(metrics["tbr_percent"], ok_max=4, warn_max=8, higher_is_worse=True)
    cv_icon = _status_icon(metrics["cv_percent"], ok_max=36, warn_max=45, higher_is_worse=True)
    gmi_icon = _status_icon(metrics["gmi_percent"], ok_max=7.0, warn_max=8.0, higher_is_worse=True)

    return (
        f"📊 Resumen glucémico — {target_date.strftime('%d/%m/%Y')}\n"
        f"\n"
        f"{tir_icon} TIR: {metrics['tir_percent']}%  (objetivo >70%)\n"
        f"{tar_icon} TAR: {metrics['tar_percent']}%  (objetivo <25%)\n"
        f"{tbr_icon} TBR: {metrics['tbr_percent']}%  (objetivo <4%)\n"
        f"{cv_icon} CV:  {metrics['cv_percent']}%  (objetivo <36%)\n"
        f"{gmi_icon} GMI: {metrics['gmi_percent']}%  (HbA1c estimada)\n"
        f"\n"
        f"📈 Promedio: {metrics['avg_glucose']} mg/dL\n"
        f"📉 Mín/Máx: {metrics['min_glucose']:.0f} / {metrics['max_glucose']:.0f} mg/dL\n"
        f"🔢 Lecturas: {metrics['reading_count']}\n"
        f"⚡ Episodios — hipo: {metrics['hypo_episodes']} | hiper: {metrics['hyper_episodes']}"
    )


# =========================================================
# Helpers
# =========================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_local_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def severity_prefix(level: str) -> str:
    mapping = {
        "INFO": "ℹ️",
        "WARN": "⚠️",
        "HIGH": "🚨",
        "CRITICAL": "🆘",
        "RISE": "📈",
        "DROP": "📉",
        "OK": "✅",
    }
    return mapping.get(level.upper(), "ℹ️")


def notify_telegram(title: str, body: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram no configurado.")
        return

    message = f"{title}\n\n{body}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()


def emit_alert(level: str, alert_code: str, title: str, body: str, state: dict) -> None:
    full_title = f"{severity_prefix(level)} {title}"
    logger.warning("%s | %s | %s", alert_code, full_title, body.replace("\n", " | "))
    try:
        notify_telegram(full_title, body)
    except Exception as exc:
        logger.warning("No se pudo enviar Telegram: %s", exc)
    mark_alert(state, alert_code)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {
            "previous_reading": None,
            "out_of_range_start": None,
            "out_of_range_type": None,
            "last_alerts": {},
        }
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "previous_reading": None,
            "out_of_range_start": None,
            "out_of_range_type": None,
            "last_alerts": {},
        }


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def in_cooldown(state: dict[str, Any], key: str) -> bool:
    raw = state["last_alerts"].get(key)
    if not raw:
        return False
    last = parse_dt(raw)
    if last is None:
        return False
    minutes = (now_utc() - last).total_seconds() / 60
    return minutes < COOLDOWN_MINUTES


def mark_alert(state: dict[str, Any], key: str) -> None:
    state["last_alerts"][key] = now_utc().isoformat()


def classify_range(glucose: float | None) -> str | None:
    if glucose is None:
        return None
    if glucose < LOW_THRESHOLD:
        return "low"
    if glucose > HIGH_THRESHOLD:
        return "high"
    return "normal"


def classify_absolute_severity(glucose: float | None) -> tuple[str, str]:
    if glucose is None:
        return "INFO", "sin_dato"
    if glucose < VERY_LOW_THRESHOLD:
        return "CRITICAL", "muy_baja"
    if glucose < LOW_THRESHOLD:
        return "HIGH", "baja"
    if glucose > VERY_HIGH_THRESHOLD:
        return "CRITICAL", "muy_alta"
    if glucose > HIGH_THRESHOLD:
        return "HIGH", "alta"
    return "OK", "en_rango"


def reading_to_dict(reading: Any) -> dict[str, Any]:
    ts = getattr(reading, "timestamp", None)
    value = getattr(reading, "value_in_mg_per_dl", None)
    if value is None:
        value = getattr(reading, "value", None)
    trend = getattr(reading, "trend", None)

    return {
        "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        "glucose_mgdl": float(value) if value is not None else None,
        "trend": str(trend) if trend is not None else None,
    }


def calc_metrics(prev: dict[str, Any] | None, curr: dict[str, Any]) -> dict[str, float] | None:
    if not prev:
        return None

    prev_g = prev.get("glucose_mgdl")
    curr_g = curr.get("glucose_mgdl")
    prev_ts = parse_dt(prev.get("timestamp"))
    curr_ts = parse_dt(curr.get("timestamp"))

    if prev_g is None or curr_g is None or prev_ts is None or curr_ts is None:
        return None

    dt_min = (curr_ts - prev_ts).total_seconds() / 60
    if dt_min <= 0:
        return None

    delta = curr_g - prev_g
    slope = delta / dt_min
    pct = (delta / prev_g) * 100 if prev_g != 0 else 0.0

    return {
        "delta_mgdl": delta,
        "dt_min": dt_min,
        "slope_mgdl_min": slope,
        "percent_change": pct,
    }


# =========================================================
# Persistencia de lecturas
# =========================================================
def get_daily_csv_path(ts: str) -> Path:
    dt = parse_dt(ts)
    if dt is None:
        day = datetime.now().strftime("%Y-%m-%d")
    else:
        day = dt.astimezone().strftime("%Y-%m-%d")
    return DATA_DIR / f"glucose_{day}.csv"


def persist_reading(curr: dict[str, Any], metrics: dict[str, float] | None) -> None:
    """Persiste la lectura en CSV (compatibilidad) y en DuckDB."""
    range_type = classify_range(curr["glucose_mgdl"]) or "normal"

    # ── CSV ────────────────────────────────────────────────────────────────────
    path = get_daily_csv_path(curr["timestamp"])
    file_exists = path.exists()
    row = {
        "timestamp": curr["timestamp"],
        "glucose_mgdl": curr["glucose_mgdl"],
        "trend": curr["trend"],
        "delta_mgdl": metrics["delta_mgdl"] if metrics else None,
        "dt_min": metrics["dt_min"] if metrics else None,
        "slope_mgdl_min": metrics["slope_mgdl_min"] if metrics else None,
        "percent_change": metrics["percent_change"] if metrics else None,
        "range_type": range_type,
    }
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    # ── DuckDB ─────────────────────────────────────────────────────────────────
    ts = parse_dt(curr["timestamp"])
    if ts and curr["glucose_mgdl"] is not None:
        try:
            db_insert_reading(
                timestamp=ts,
                glucose_mgdl=float(curr["glucose_mgdl"]),
                trend=curr.get("trend"),
                delta_mgdl=metrics["delta_mgdl"] if metrics else None,
                dt_min=metrics["dt_min"] if metrics else None,
                slope_mgdl_min=metrics["slope_mgdl_min"] if metrics else None,
                percent_change=metrics["percent_change"] if metrics else None,
                range_type=range_type,
            )
        except Exception as exc:
            logger.warning("Error escribiendo en DuckDB: %s", exc)


# =========================================================
# Gráfico diario único (un archivo por día, se sobreescribe)
# =========================================================
_last_chart_date: Optional[date] = None
_last_summary_date: Optional[date] = None


def render_daily_chart() -> None:
    """
    Genera UN solo chart por día desde DuckDB.
    El archivo se llama glucose_YYYY-MM-DD.png y se sobreescribe en cada poll.
    Incluye zonas de color, umbrales y métricas AGP en el título.
    """
    global _last_chart_date

    if not SAVE_PLOT:
        return

    today = date.today()
    df = db_get_day(today)

    if df.empty or len(df) < 2:
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")

    metrics = calculate_agp_metrics(df)

    fig, ax = plt.subplots(figsize=(14, 6))

    # ── Zonas de color ─────────────────────────────────────────────────────────
    ax.axhspan(VERY_LOW_THRESHOLD, LOW_THRESHOLD, alpha=0.12, color="#FF6B6B", label="Hipo leve")
    ax.axhspan(0, VERY_LOW_THRESHOLD, alpha=0.18, color="#C0392B", label="Hipo severa")
    ax.axhspan(HIGH_THRESHOLD, VERY_HIGH_THRESHOLD, alpha=0.12, color="#F39C12", label="Hiper leve")
    ax.axhspan(VERY_HIGH_THRESHOLD, 400, alpha=0.15, color="#E74C3C", label="Hiper severa")
    ax.axhspan(LOW_THRESHOLD, HIGH_THRESHOLD, alpha=0.08, color="#2ECC71", label="En rango")

    # ── Líneas de umbral ───────────────────────────────────────────────────────
    ax.axhline(LOW_THRESHOLD, color="#E74C3C", linestyle="--", linewidth=1.2, alpha=0.7)
    ax.axhline(HIGH_THRESHOLD, color="#E74C3C", linestyle="--", linewidth=1.2, alpha=0.7)
    ax.axhline(VERY_LOW_THRESHOLD, color="#8E44AD", linestyle=":", linewidth=1.0, alpha=0.7)
    ax.axhline(VERY_HIGH_THRESHOLD, color="#8E44AD", linestyle=":", linewidth=1.0, alpha=0.7)

    # ── Línea de glucosa con puntos ───────────────────────────────────────────
    ax.plot(df["timestamp"], df["glucose_mgdl"],
            color="#2C3E50", linewidth=2, marker="o", markersize=4, zorder=5)

    # ── Formato ejes ──────────────────────────────────────────────────────────
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.xticks(rotation=45)
    ax.set_ylim(0, max(350, float(df["glucose_mgdl"].max()) + 30))
    ax.set_xlabel("Hora del día", fontsize=11)
    ax.set_ylabel("Glucosa (mg/dL)", fontsize=11)
    ax.grid(True, alpha=0.3)

    # ── Título con métricas ───────────────────────────────────────────────────
    if metrics:
        title = (
            f"Glucosa — {today.strftime('%d/%m/%Y')}  |  "
            f"TIR {metrics['tir_percent']}%  •  "
            f"Prom {metrics['avg_glucose']} mg/dL  •  "
            f"CV {metrics['cv_percent']}%  •  "
            f"GMI {metrics['gmi_percent']}%"
        )
    else:
        title = f"Glucosa — {today.strftime('%d/%m/%Y')}"
    ax.set_title(title, fontsize=12, fontweight="bold")

    ax.legend(loc="upper right", fontsize=8, framealpha=0.7)
    plt.tight_layout()

    # ── Guardar: un archivo por día (sobreescribe) ────────────────────────────
    out_path = CHART_DIR / f"glucose_{today}.png"
    fig.savefig(out_path, dpi=120)
    plt.close(fig)

    _last_chart_date = today
    logger.info("Chart diario actualizado: %s (%d lecturas)", out_path.name, len(df))


def send_daily_summary(target_date: date) -> None:
    """
    Calcula las métricas AGP del día y envía el resumen por Telegram.
    Se llama al detectar cambio de día (medianoche).
    """
    global _last_summary_date

    if _last_summary_date == target_date:
        return

    df = db_get_day(target_date)
    if df.empty or len(df) < 3:
        logger.info("Datos insuficientes para resumen diario de %s", target_date)
        return

    metrics = calculate_agp_metrics(df)
    if not metrics:
        return

    metrics["date"] = target_date
    metrics["llm_summary"] = None

    try:
        db_upsert_summary(metrics)
    except Exception as exc:
        logger.warning("Error guardando resumen en DuckDB: %s", exc)

    message = format_daily_summary_telegram(metrics, target_date)
    logger.info("Enviando resumen diario:\n%s", message)
    try:
        notify_telegram("📊 Resumen del día", message)
        _last_summary_date = target_date
    except Exception as exc:
        logger.warning("Error enviando resumen diario por Telegram: %s", exc)


# =========================================================
# Reglas de alerta
# =========================================================
def check_no_data(state: dict[str, Any], curr: dict[str, Any]) -> None:
    curr_ts = parse_dt(curr["timestamp"])
    if curr_ts is None:
        return

    lag_min = (now_utc() - curr_ts).total_seconds() / 60
    if lag_min >= NO_DATA_ALERT_MINUTES and not in_cooldown(state, "no_data"):
        emit_alert(
            "WARN",
            "no_data",
            "Sin datos recientes",
            (
                f"Última lectura con {lag_min:.0f} min de antigüedad.\n"
                f"Objetivo actual: mantener monitoreo activo.\n"
                f"Umbrales: baja < {LOW_THRESHOLD}, alta > {HIGH_THRESHOLD}"
            ),
            state,
        )


def check_absolute_thresholds(state: dict[str, Any], curr: dict[str, Any]) -> None:
    g = curr["glucose_mgdl"]
    if g is None:
        return

    severity, status = classify_absolute_severity(g)

    if status == "muy_baja" and not in_cooldown(state, "very_low"):
        emit_alert(
            severity,
            "very_low",
            "Glucosa MUY BAJA",
            (
                f"Lectura actual: {g:.0f} mg/dL\n"
                f"Clasificación: por debajo de {VERY_LOW_THRESHOLD}\n"
                f"Rango de referencia: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )

    elif status == "baja" and not in_cooldown(state, "low"):
        emit_alert(
            severity,
            "low",
            "Glucosa BAJA",
            (
                f"Lectura actual: {g:.0f} mg/dL\n"
                f"Clasificación: por debajo de {LOW_THRESHOLD}\n"
                f"Rango de referencia: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )

    elif status == "muy_alta" and not in_cooldown(state, "very_high"):
        emit_alert(
            severity,
            "very_high",
            "Glucosa MUY ALTA",
            (
                f"Lectura actual: {g:.0f} mg/dL\n"
                f"Clasificación: por encima de {VERY_HIGH_THRESHOLD}\n"
                f"Rango de referencia: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )

    elif status == "alta" and not in_cooldown(state, "high"):
        emit_alert(
            severity,
            "high",
            "Glucosa ALTA",
            (
                f"Lectura actual: {g:.0f} mg/dL\n"
                f"Clasificación: por encima de {HIGH_THRESHOLD}\n"
                f"Rango de referencia: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )


def check_persistence(state: dict[str, Any], curr: dict[str, Any]) -> None:
    g = curr["glucose_mgdl"]
    range_type = classify_range(g)

    if range_type == "normal":
        state["out_of_range_start"] = None
        state["out_of_range_type"] = None
        return

    if state["out_of_range_type"] != range_type:
        state["out_of_range_type"] = range_type
        state["out_of_range_start"] = now_utc().isoformat()
        return

    start = parse_dt(state["out_of_range_start"])
    if start is None:
        state["out_of_range_start"] = now_utc().isoformat()
        return

    minutes = (now_utc() - start).total_seconds() / 60
    if minutes >= PERSISTENCE_MINUTES:
        key = f"persistent_{range_type}"
        if not in_cooldown(state, key):
            direction = "por debajo" if range_type == "low" else "por encima"
            emit_alert(
                "HIGH",
                key,
                "Fuera de rango sostenido",
                (
                    f"Glucosa actual: {g:.0f} mg/dL\n"
                    f"Estado: {direction} del rango\n"
                    f"Tiempo fuera de rango: {minutes:.0f} min\n"
                    f"Rango objetivo: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
                ),
                state,
            )


def check_rapid_change(state: dict[str, Any], prev: dict[str, Any] | None, curr: dict[str, Any]) -> None:
    metrics = calc_metrics(prev, curr)
    if metrics is None:
        return

    slope = metrics["slope_mgdl_min"]
    pct = metrics["percent_change"]
    delta = metrics["delta_mgdl"]
    dt_min = metrics["dt_min"]

    current_range = classify_range(curr["glucose_mgdl"])
    current_status = "EN RANGO"
    if current_range == "low":
        current_status = "BAJA"
    elif current_range == "high":
        current_status = "ALTA"

    if (slope <= RAPID_DROP_MGDL_MIN or pct <= RAPID_DROP_PERCENT) and not in_cooldown(state, "rapid_drop_any"):
        emit_alert(
            "DROP",
            "rapid_drop_any",
            "Evento detectado: caída brusca",
            (
                f"Estado actual: {current_status}\n"
                f"Lectura previa: {prev['glucose_mgdl']:.0f} mg/dL\n"
                f"Lectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
                f"Cambio: {delta:.1f} mg/dL en {dt_min:.1f} min\n"
                f"Pendiente: {slope:.2f} mg/dL/min\n"
                f"Variación: {pct:.2f}%\n"
                f"Umbrales vigentes: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )

    if (slope >= RAPID_RISE_MGDL_MIN or pct >= RAPID_RISE_PERCENT) and not in_cooldown(state, "rapid_rise_any"):
        emit_alert(
            "RISE",
            "rapid_rise_any",
            "Evento detectado: subida brusca",
            (
                f"Estado actual: {current_status}\n"
                f"Lectura previa: {prev['glucose_mgdl']:.0f} mg/dL\n"
                f"Lectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
                f"Cambio: {delta:.1f} mg/dL en {dt_min:.1f} min\n"
                f"Pendiente: {slope:.2f} mg/dL/min\n"
                f"Variación: {pct:.2f}%\n"
                f"Umbrales vigentes: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )

    if slope <= EXTREME_DROP_MGDL_MIN and not in_cooldown(state, "extreme_drop"):
        emit_alert(
            "CRITICAL",
            "extreme_drop",
            "Evento crítico: caída extrema",
            (
                f"Estado actual: {current_status}\n"
                f"Lectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
                f"Pendiente extrema: {slope:.2f} mg/dL/min\n"
                f"Umbrales vigentes: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )

    if slope >= EXTREME_RISE_MGDL_MIN and not in_cooldown(state, "extreme_rise"):
        emit_alert(
            "CRITICAL",
            "extreme_rise",
            "Evento crítico: subida extrema",
            (
                f"Estado actual: {current_status}\n"
                f"Lectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
                f"Pendiente extrema: {slope:.2f} mg/dL/min\n"
                f"Umbrales vigentes: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
            ),
            state,
        )


def build_peak_context(curr_glucose: float | None) -> str:
    range_type = classify_range(curr_glucose)
    if range_type == "normal":
        return "dentro de rango"
    if range_type == "low":
        return "fuera de rango por debajo"
    if range_type == "high":
        return "fuera de rango por encima"
    return "sin contexto"


def print_status(curr: dict[str, Any], prev: dict[str, Any] | None) -> None:
    severity, status = classify_absolute_severity(curr["glucose_mgdl"])
    metrics = calc_metrics(prev, curr)

    logger.info(
        "%s ESTADO ACTUAL | glucosa=%s mg/dL | clasificacion=%s | tendencia=%s | umbrales=%s-%s",
        severity_prefix(severity),
        curr["glucose_mgdl"],
        status,
        curr["trend"],
        LOW_THRESHOLD,
        HIGH_THRESHOLD,
    )

    if metrics:
        logger.info(
            "ℹ️ CAMBIO RECIENTE | delta=%.1f mg/dL | minutos=%.1f | pendiente=%.2f mg/dL/min | variación=%.2f%%",
            metrics["delta_mgdl"],
            metrics["dt_min"],
            metrics["slope_mgdl_min"],
            metrics["percent_change"],
        )
    else:
        logger.info("ℹ️ CAMBIO RECIENTE | sin lectura previa para comparar.")


def get_recent_history(patient: Any) -> list[dict[str, Any]]:
    """
    Trae historial reciente desde LibreLinkUp usando graph().
    Devuelve lista ordenada por timestamp.
    """
    history = []

    try:
        graph_data = client.graph(patient)

        # Si graph_data ya es iterable de puntos
        if isinstance(graph_data, list):
            raw_points = graph_data
        else:
            # fallback por si viene en objeto con atributos
            raw_points = getattr(graph_data, "graph_data", None)
            if raw_points is None:
                raw_points = getattr(graph_data, "data", None)
            if raw_points is None:
                raw_points = []

        for point in raw_points:
            ts = getattr(point, "timestamp", None)
            value = getattr(point, "value_in_mg_per_dl", None)
            if value is None:
                value = getattr(point, "value", None)

            trend = getattr(point, "trend", None)

            row = {
                "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "glucose_mgdl": float(value) if value is not None else None,
                "trend": str(trend) if trend is not None else None,
            }

            if row["glucose_mgdl"] is not None and row["timestamp"] not in (None, "None"):
                history.append(row)

    except Exception as exc:
        logger.warning("No se pudo obtener graph() del paciente: %s", exc)

    history = sorted(
        history,
        key=lambda x: parse_dt(x["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc)
    )

    return history


def analyze_recent_history_on_start(state: dict[str, Any], history: list[dict[str, Any]]) -> None:
    """
    Evalúa estado actual + eventos recientes con el histórico ya existente.
    """
    if not history:
        logger.info("No hay histórico reciente disponible para analizar al inicio.")
        return

    curr = history[-1]
    prev = history[-2] if len(history) >= 2 else None

    logger.info("Analizando histórico reciente al inicio...")
    print_status(curr, prev)

    # Umbral actual siempre
    check_absolute_thresholds(state, curr)

    # Persistencia: recorrer varias lecturas recientes
    for row in history[-12:]:
        check_persistence(state, row)

    # Evento reciente usando las dos últimas
    if prev is not None:
        check_rapid_change(state, prev, curr)

    state["previous_reading"] = curr
    save_state(state)

def send_combined_alert(current_status: str, current_value: float, alerts: list[str]) -> None:
    if not alerts:
        return

    title = "🚨 ALERTA DE GLUCOSA"
    body = (
        f"Estado actual: {current_status}\n"
        f"Lectura actual: {current_value:.0f} mg/dL\n"
        f"Umbrales vigentes: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL\n\n"
        "Eventos detectados:\n- " + "\n- ".join(alerts)
    )

    logger.warning("%s | %s", title, body.replace("\n", " | "))
    try:
        notify_telegram(title, body)
    except Exception as exc:
        logger.warning("No se pudo enviar Telegram: %s", exc)

# =========================================================
# Main
# =========================================================
def get_patient_id_or_obj(patients: list[Any]) -> Any:
    if len(patients) == 1:
        return patients[0]

    print("Pacientes disponibles:")
    for idx, patient in enumerate(patients, start=1):
        print(f"{idx}. {patient}")

    selection = input("Selecciona el número del paciente a monitorear: ").strip()
    selected = int(selection) - 1
    return patients[selected]


def main() -> None:
    # ── Inicializar DuckDB ────────────────────────────────────────────────────
    logger.info("Inicializando base de datos DuckDB...")
    init_db()

    # ── Migrar CSVs históricos ────────────────────────────────────────────────
    migrated = migrate_csv_to_db()
    if migrated > 0:
        logger.info("Migradas %d lecturas de CSV histórico a DuckDB.", migrated)

    # ── Autenticación LibreLinkUp ─────────────────────────────────────────────
    logger.info("Autenticando con LibreLinkUp...")
    client.authenticate()

    patients = client.get_patients()
    if not patients:
        raise RuntimeError("No se encontraron pacientes compartidos en tu cuenta.")

    patient = get_patient_id_or_obj(patients)
    logger.info("Monitoreando paciente: %s", patient)

    state = load_state()

    # ── Análisis inicial con histórico reciente ───────────────────────────────
    history = get_recent_history(patient)

    if history:
        logger.info("Se encontraron %s puntos históricos recientes.", len(history))
        for i, row in enumerate(history):
            prev_row = history[i - 1] if i > 0 else None
            metrics = calc_metrics(prev_row, row) if prev_row else None
            persist_reading(row, metrics)

        analyze_recent_history_on_start(state, history)
        render_daily_chart()
    else:
        logger.info("No se encontró histórico reciente; se usará solo lectura en vivo.")

    # ── Monitoreo continuo ────────────────────────────────────────────────────
    current_day = date.today()

    while True:
        try:
            latest = client.latest(patient_identifier=patient)
            curr = reading_to_dict(latest)
            prev = state.get("previous_reading")

            print_status(curr, prev)

            metrics = calc_metrics(prev, curr)
            persist_reading(curr, metrics)

            check_absolute_thresholds(state, curr)

            if prev is not None:
                check_no_data(state, curr)
                check_persistence(state, curr)
                check_rapid_change(state, prev, curr)

            state["previous_reading"] = curr
            save_state(state)

            # ── Chart diario único (se actualiza en cada poll) ────────────────
            render_daily_chart()

            # ── Detectar cambio de día → enviar resumen del día anterior ──────
            new_day = date.today()
            if new_day != current_day:
                logger.info("Nuevo día detectado. Enviando resumen de %s...", current_day)
                send_daily_summary(current_day)
                current_day = new_day

            time.sleep(POLL_SECONDS)

        except LLUAPIRateLimitError as exc:
            retry_after = getattr(exc, "retry_after", None) or 300
            logger.warning("Rate limit. Esperando %s segundos...", retry_after)
            time.sleep(retry_after)

        except KeyboardInterrupt:
            logger.info("Saliendo. Enviando resumen final...")
            send_daily_summary(date.today())
            break

        except Exception as exc:
            logger.warning("Error en el ciclo: %s", exc)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()