"""
Monitor de glucosa continuo — escribe lecturas via FastAPI (POST /api/readings).
Fuente de datos: LibreLinkUp (FreeStyle Libre CGM).
Alertas: Telegram.
Fallback: CSV local si la API no esta disponible.
"""

import csv
import json
import logging
import os
import time
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Optional

import requests as http_requests
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
LOG_FILE = Path("glucose_monitor.log")

DATA_DIR.mkdir(exist_ok=True)

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
# Configuracion
# =========================================================
LIBRE_EMAIL = os.getenv("LIBRE_EMAIL")
LIBRE_PASSWORD = os.getenv("LIBRE_PASSWORD")
LIBRE_REGION = os.getenv("LIBRE_REGION", "LA").upper()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

API_URL = os.getenv("API_URL", "http://localhost:8888")
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
# API Client — escribe lecturas via FastAPI
# =========================================================
def api_health_check() -> bool:
    """Verifica si la API esta disponible."""
    try:
        r = http_requests.get(f"{API_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def api_post_reading(reading_data: dict) -> bool:
    """
    Envia una lectura al API (POST /api/readings).
    Retorna True si la API respondio (201 creado o 200 duplicado).
    Retorna False si la API no esta disponible.
    """
    try:
        r = http_requests.post(
            f"{API_URL}/api/readings",
            json=reading_data,
            timeout=10,
        )
        return r.status_code in (200, 201)
    except Exception as exc:
        logger.warning("API no disponible para POST: %s", exc)
        return False


def api_get_daily_summary(target_date: date) -> Optional[dict]:
    """Obtiene el resumen diario desde la API."""
    try:
        r = http_requests.get(
            f"{API_URL}/api/summaries/day/{target_date}",
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        logger.warning("API no disponible para GET summary: %s", exc)
    return None


# =========================================================
# Helpers
# =========================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> Optional[datetime]:
    """
    Parsea timestamp a datetime con timezone.
    LibreLinkUp devuelve timestamps en hora local SIN timezone.
    Si no tiene tz, asumimos la zona horaria del sistema (no UTC).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo:
            return value
        return value.astimezone()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed
        return parsed.astimezone()
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
    response = http_requests.post(url, json=payload, timeout=15)
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


def classify_range(glucose: Optional[float]) -> Optional[str]:
    if glucose is None:
        return None
    if glucose < VERY_LOW_THRESHOLD:
        return "very_low"
    if glucose < LOW_THRESHOLD:
        return "low"
    if glucose > VERY_HIGH_THRESHOLD:
        return "very_high"
    if glucose > HIGH_THRESHOLD:
        return "high"
    return "normal"


def classify_absolute_severity(glucose: Optional[float]) -> tuple[str, str]:
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

    # Asegurar timezone en el timestamp
    if isinstance(ts, datetime) and ts.tzinfo is None:
        ts = ts.astimezone()

    return {
        "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        "glucose_mgdl": float(value) if value is not None else None,
        "trend": str(trend) if trend is not None else None,
    }


def calc_metrics(prev: Optional[dict[str, Any]], curr: dict[str, Any]) -> Optional[dict[str, float]]:
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
# Persistencia: API + CSV fallback
# =========================================================
def get_daily_csv_path(ts: str) -> Path:
    dt = parse_dt(ts)
    if dt is None:
        day = datetime.now().strftime("%Y-%m-%d")
    else:
        day = dt.astimezone().strftime("%Y-%m-%d")
    return DATA_DIR / f"glucose_{day}.csv"


def persist_reading(curr: dict[str, Any], metrics: Optional[dict[str, float]]) -> None:
    """Persiste la lectura via API (primario) y CSV (fallback)."""
    range_type = classify_range(curr["glucose_mgdl"]) or "normal"

    # Datos para API y CSV
    reading_data = {
        "timestamp": curr["timestamp"],
        "glucose_mgdl": curr["glucose_mgdl"],
        "trend": curr["trend"],
        "delta_mgdl": metrics["delta_mgdl"] if metrics else None,
        "dt_min": metrics["dt_min"] if metrics else None,
        "slope_mgdl_min": metrics["slope_mgdl_min"] if metrics else None,
        "percent_change": metrics["percent_change"] if metrics else None,
        "range_type": range_type,
    }

    # 1. Enviar a la API (primario)
    api_ok = api_post_reading(reading_data)
    if not api_ok:
        logger.warning("Lectura guardada solo en CSV (API no disponible): %s mg/dL",
                        curr["glucose_mgdl"])

    # 2. CSV siempre como respaldo
    path = get_daily_csv_path(curr["timestamp"])
    file_exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=reading_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(reading_data)


# =========================================================
# Resumen diario via API
# =========================================================
_last_summary_date: Optional[date] = None


def _status_icon(value: float, ok_max: float, warn_max: float, higher_is_worse: bool = True) -> str:
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


def send_daily_summary(target_date: date) -> None:
    """Obtiene resumen del dia desde la API y lo envia por Telegram."""
    global _last_summary_date

    if _last_summary_date == target_date:
        return

    summary = api_get_daily_summary(target_date)
    if not summary or not summary.get("reading_count"):
        logger.info("Sin datos suficientes para resumen diario de %s", target_date)
        return

    # Formatear mensaje para Telegram
    tir_icon = _status_icon(summary["tir_percent"], ok_max=70, warn_max=50, higher_is_worse=False)
    tar_icon = _status_icon(summary["tar_percent"], ok_max=25, warn_max=40, higher_is_worse=True)
    tbr_icon = _status_icon(summary["tbr_percent"], ok_max=4, warn_max=8, higher_is_worse=True)
    cv_icon = _status_icon(summary["cv_percent"], ok_max=36, warn_max=45, higher_is_worse=True)
    gmi_icon = _status_icon(summary["gmi_percent"], ok_max=7.0, warn_max=8.0, higher_is_worse=True)

    message = (
        f"📊 Resumen glucemico — {target_date.strftime('%d/%m/%Y')}\n"
        f"\n"
        f"{tir_icon} TIR: {summary['tir_percent']}%  (objetivo >70%)\n"
        f"{tar_icon} TAR: {summary['tar_percent']}%  (objetivo <25%)\n"
        f"{tbr_icon} TBR: {summary['tbr_percent']}%  (objetivo <4%)\n"
        f"{cv_icon} CV:  {summary['cv_percent']}%  (objetivo <36%)\n"
        f"{gmi_icon} GMI: {summary['gmi_percent']}%  (HbA1c estimada)\n"
        f"\n"
        f"📈 Promedio: {summary['avg_glucose_mgdl']} mg/dL\n"
        f"📉 Min/Max: {summary['min_glucose_mgdl']:.0f} / {summary['max_glucose_mgdl']:.0f} mg/dL\n"
        f"🔢 Lecturas: {summary['reading_count']}\n"
        f"⚡ Episodios — hipo: {summary['hypo_episodes']} | hiper: {summary['hyper_episodes']}"
    )

    logger.info("Enviando resumen diario:\n%s", message)
    try:
        notify_telegram("📊 Resumen del dia", message)
        _last_summary_date = target_date
    except Exception as exc:
        logger.warning("Error enviando resumen diario por Telegram: %s", exc)


# =========================================================
# Estado de la lectura y alertas
# =========================================================
def print_status(curr: dict[str, Any], prev: Optional[dict[str, Any]]) -> None:
    severity, status = classify_absolute_severity(curr["glucose_mgdl"])
    metrics = calc_metrics(prev, curr)

    curr_ts = parse_dt(curr.get("timestamp"))
    lag_min = round((now_utc() - curr_ts).total_seconds() / 60, 1) if curr_ts else None
    lag_str = f"{lag_min} min atras" if lag_min is not None else "timestamp desconocido"

    logger.info(
        "%s ESTADO ACTUAL | glucosa=%s mg/dL | ts=%s (%s) | clasificacion=%s | tendencia=%s | umbrales=%s-%s",
        severity_prefix(severity),
        curr["glucose_mgdl"],
        curr.get("timestamp"),
        lag_str,
        status,
        curr["trend"],
        LOW_THRESHOLD,
        HIGH_THRESHOLD,
    )

    if metrics:
        logger.info(
            "ℹ️ CAMBIO RECIENTE | delta=%.1f mg/dL | minutos=%.1f | pendiente=%.2f mg/dL/min | variacion=%.2f%%",
            metrics["delta_mgdl"],
            metrics["dt_min"],
            metrics["slope_mgdl_min"],
            metrics["percent_change"],
        )
    else:
        logger.info("ℹ️ CAMBIO RECIENTE | sin lectura previa para comparar.")


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
            "WARN", "no_data", "Sin datos recientes",
            f"Ultima lectura con {lag_min:.0f} min de antiguedad.\n"
            f"Objetivo actual: mantener monitoreo activo.\n"
            f"Umbrales: baja < {LOW_THRESHOLD}, alta > {HIGH_THRESHOLD}",
            state,
        )


def check_absolute_thresholds(state: dict[str, Any], curr: dict[str, Any]) -> None:
    g = curr["glucose_mgdl"]
    if g is None:
        return

    severity, status = classify_absolute_severity(g)

    if status == "muy_baja" and not in_cooldown(state, "very_low"):
        emit_alert(severity, "very_low", "Glucosa MUY BAJA",
                   f"Lectura actual: {g:.0f} mg/dL\nClasificacion: por debajo de {VERY_LOW_THRESHOLD}\nRango: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                   state)
    elif status == "baja" and not in_cooldown(state, "low"):
        emit_alert(severity, "low", "Glucosa BAJA",
                   f"Lectura actual: {g:.0f} mg/dL\nClasificacion: por debajo de {LOW_THRESHOLD}\nRango: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                   state)
    elif status == "muy_alta" and not in_cooldown(state, "very_high"):
        emit_alert(severity, "very_high", "Glucosa MUY ALTA",
                   f"Lectura actual: {g:.0f} mg/dL\nClasificacion: por encima de {VERY_HIGH_THRESHOLD}\nRango: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                   state)
    elif status == "alta" and not in_cooldown(state, "high"):
        emit_alert(severity, "high", "Glucosa ALTA",
                   f"Lectura actual: {g:.0f} mg/dL\nClasificacion: por encima de {HIGH_THRESHOLD}\nRango: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                   state)


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
            direction = "por debajo" if "low" in range_type else "por encima"
            emit_alert(
                "HIGH", key, "Fuera de rango sostenido",
                f"Glucosa actual: {g:.0f} mg/dL\nEstado: {direction} del rango\n"
                f"Tiempo fuera de rango: {minutes:.0f} min\nRango objetivo: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                state,
            )


def check_rapid_change(state: dict[str, Any], prev: Optional[dict[str, Any]], curr: dict[str, Any]) -> None:
    metrics = calc_metrics(prev, curr)
    if metrics is None:
        return

    slope = metrics["slope_mgdl_min"]
    pct = metrics["percent_change"]
    delta = metrics["delta_mgdl"]
    dt_min = metrics["dt_min"]

    current_range = classify_range(curr["glucose_mgdl"])
    current_status = {"low": "BAJA", "high": "ALTA"}.get(current_range, "EN RANGO")

    change_body = (
        f"Estado actual: {current_status}\n"
        f"Lectura previa: {prev['glucose_mgdl']:.0f} mg/dL\n"
        f"Lectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
        f"Cambio: {delta:.1f} mg/dL en {dt_min:.1f} min\n"
        f"Pendiente: {slope:.2f} mg/dL/min\n"
        f"Variacion: {pct:.2f}%\n"
        f"Umbrales vigentes: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL"
    )

    if (slope <= RAPID_DROP_MGDL_MIN or pct <= RAPID_DROP_PERCENT) and not in_cooldown(state, "rapid_drop_any"):
        emit_alert("DROP", "rapid_drop_any", "Evento detectado: caida brusca", change_body, state)

    if (slope >= RAPID_RISE_MGDL_MIN or pct >= RAPID_RISE_PERCENT) and not in_cooldown(state, "rapid_rise_any"):
        emit_alert("RISE", "rapid_rise_any", "Evento detectado: subida brusca", change_body, state)

    if slope <= EXTREME_DROP_MGDL_MIN and not in_cooldown(state, "extreme_drop"):
        emit_alert("CRITICAL", "extreme_drop", "Evento critico: caida extrema",
                   f"Estado actual: {current_status}\nLectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
                   f"Pendiente extrema: {slope:.2f} mg/dL/min\nUmbrales: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                   state)

    if slope >= EXTREME_RISE_MGDL_MIN and not in_cooldown(state, "extreme_rise"):
        emit_alert("CRITICAL", "extreme_rise", "Evento critico: subida extrema",
                   f"Estado actual: {current_status}\nLectura actual: {curr['glucose_mgdl']:.0f} mg/dL\n"
                   f"Pendiente extrema: {slope:.2f} mg/dL/min\nUmbrales: {LOW_THRESHOLD}-{HIGH_THRESHOLD} mg/dL",
                   state)


# =========================================================
# Historial reciente desde LibreLinkUp
# =========================================================
def get_recent_history(patient: Any) -> list[dict[str, Any]]:
    """Trae historial reciente desde LibreLinkUp usando graph()."""
    history: list[dict[str, Any]] = []
    try:
        graph_data = client.graph(patient)
        raw_points = graph_data if isinstance(graph_data, list) else (
            getattr(graph_data, "graph_data", None) or
            getattr(graph_data, "data", None) or []
        )
        for point in raw_points:
            row = reading_to_dict(point)
            if row["glucose_mgdl"] is not None and row["timestamp"] not in (None, "None"):
                history.append(row)
    except Exception as exc:
        logger.warning("No se pudo obtener graph() del paciente: %s", exc)

    return sorted(
        history,
        key=lambda x: parse_dt(x["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc)
    )


def analyze_recent_history_on_start(state: dict[str, Any], history: list[dict[str, Any]]) -> None:
    """Evalua estado actual + eventos recientes al arrancar."""
    if not history:
        logger.info("No hay historico reciente disponible para analizar al inicio.")
        return

    curr = history[-1]
    prev = history[-2] if len(history) >= 2 else None

    logger.info("Analizando historico reciente al inicio...")
    print_status(curr, prev)

    check_absolute_thresholds(state, curr)
    for row in history[-12:]:
        check_persistence(state, row)
    if prev is not None:
        check_rapid_change(state, prev, curr)

    state["previous_reading"] = curr
    save_state(state)


# =========================================================
# Main
# =========================================================
def get_patient_id_or_obj(patients: list[Any]) -> Any:
    if len(patients) == 1:
        return patients[0]
    print("Pacientes disponibles:")
    for idx, patient in enumerate(patients, start=1):
        print(f"{idx}. {patient}")
    selection = input("Selecciona el numero del paciente a monitorear: ").strip()
    return patients[int(selection) - 1]


def wait_for_api(max_retries: int = 15, delay: float = 3.0) -> bool:
    """Espera a que la API este disponible. Retorna True si conecta."""
    for attempt in range(1, max_retries + 1):
        if api_health_check():
            logger.info("API conectada en %s", API_URL)
            return True
        logger.info("Esperando API (%d/%d)...", attempt, max_retries)
        time.sleep(delay)
    logger.warning("API no disponible despues de %d intentos. Modo CSV-only.", max_retries)
    return False


def main() -> None:
    # Autenticacion LibreLinkUp
    logger.info("Autenticando con LibreLinkUp...")
    client.authenticate()

    patients = client.get_patients()
    if not patients:
        raise RuntimeError("No se encontraron pacientes compartidos en tu cuenta.")

    patient = get_patient_id_or_obj(patients)
    logger.info("Monitoreando paciente: %s", patient)

    # Esperar a que la API este lista
    api_online = wait_for_api()

    state = load_state()

    # Analisis inicial con historico reciente
    history = get_recent_history(patient)

    if history:
        logger.info("Se encontraron %s puntos historicos recientes.", len(history))
        for i, row in enumerate(history):
            prev_row = history[i - 1] if i > 0 else None
            metrics = calc_metrics(prev_row, row) if prev_row else None
            persist_reading(row, metrics)

        analyze_recent_history_on_start(state, history)
    else:
        logger.info("No se encontro historico reciente; se usara solo lectura en vivo.")

    # Monitoreo continuo
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

            # Detectar cambio de dia -> enviar resumen del dia anterior
            new_day = date.today()
            if new_day != current_day:
                logger.info("Nuevo dia detectado. Enviando resumen de %s...", current_day)
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
