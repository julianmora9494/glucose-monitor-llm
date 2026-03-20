import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
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

SHOW_PLOT = os.getenv("SHOW_PLOT", "1") == "1"
SAVE_PLOT = os.getenv("SAVE_PLOT", "1") == "1"

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


def append_reading_to_csv(curr: dict[str, Any], metrics: dict[str, float] | None) -> None:
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
        "range_type": classify_range(curr["glucose_mgdl"]),
    }

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# =========================================================
# Gráficos
# =========================================================
plt.ion()
_plot_initialized = False

def render_daily_chart():
    global _plot_initialized

    today = datetime.now().strftime("%Y-%m-%d")
    csv_path = DATA_DIR / f"glucose_{today}.csv"
    if not csv_path.exists():
        return

    df = pd.read_csv(csv_path)
    if df.empty or "timestamp" not in df.columns:
        return

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp", "glucose_mgdl"]).sort_values("timestamp")

    if df.empty:
        return

    plt.figure("Monitoreo glucosa del día", figsize=(12, 6))
    plt.clf()
    plt.plot(df["timestamp"], df["glucose_mgdl"], marker="o", linewidth=1)

    plt.axhline(LOW_THRESHOLD, linestyle="--")
    plt.axhline(HIGH_THRESHOLD, linestyle="--")
    plt.axhline(VERY_LOW_THRESHOLD, linestyle=":")
    plt.axhline(VERY_HIGH_THRESHOLD, linestyle=":")

    plt.title(f"Registro de glucosa del día - {today}")
    plt.xlabel("Hora")
    plt.ylabel("Glucosa mg/dL")
    plt.grid(True)
    plt.tight_layout()

    if SAVE_PLOT:
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        current_glucose = int(df["glucose_mgdl"].iloc[-1])
        out_path = CHART_DIR / f"glucose_{timestamp_str}_{current_glucose}mgdl.png"
        plt.savefig(out_path, dpi=120)

    if SHOW_PLOT:
        plt.pause(0.1)

    _plot_initialized = True


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
    logger.info("Autenticando con LibreLinkUp...")
    client.authenticate()

    patients = client.get_patients()
    if not patients:
        raise RuntimeError("No se encontraron pacientes compartidos en tu cuenta.")

    patient = get_patient_id_or_obj(patients)
    logger.info("Monitoreando paciente: %s", patient)

    state = load_state()

    # =====================================================
    # Análisis inicial con histórico reciente
    # =====================================================
    history = get_recent_history(patient)

    if history:
        logger.info("Se encontraron %s puntos históricos recientes.", len(history))

        # Guardar histórico en CSV
        for i, row in enumerate(history):
            prev_row = history[i - 1] if i > 0 else None
            metrics = calc_metrics(prev_row, row) if prev_row else None
            append_reading_to_csv(row, metrics)

        analyze_recent_history_on_start(state, history)
        render_daily_chart()
    else:
        logger.info("No se encontró histórico reciente; se usará solo lectura en vivo.")

    # =====================================================
    # Monitoreo continuo
    # =====================================================
    while True:
        try:
            latest = client.latest(patient_identifier=patient)
            curr = reading_to_dict(latest)
            prev = state.get("previous_reading")

            print_status(curr, prev)

            metrics = calc_metrics(prev, curr)
            append_reading_to_csv(curr, metrics)

            check_absolute_thresholds(state, curr)

            if prev is not None:
                #check_no_data(state, curr)
                check_persistence(state, curr)
                check_rapid_change(state, prev, curr)

            state["previous_reading"] = curr
            save_state(state)

            render_daily_chart()
            time.sleep(POLL_SECONDS)

        except LLUAPIRateLimitError as exc:
            retry_after = getattr(exc, "retry_after", None) or 300
            logger.warning("Rate limit. Esperando %s segundos...", retry_after)
            time.sleep(retry_after)

        except KeyboardInterrupt:
            logger.info("Saliendo...")
            break

        except Exception as exc:
            logger.warning("Error en el ciclo: %s", exc)
            time.sleep(POLL_SECONDS)
            

if __name__ == "__main__":
    main()