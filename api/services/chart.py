"""
Servicio de generación de charts clínicos.
Produce el chart AGP diario (un archivo por día) y mini-charts para el dashboard.
"""

import base64
from datetime import date
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from api.services.db import get_readings_by_date
from api.services.metrics import calculate_daily_metrics

CHART_DIR = Path("charts")
CHART_DIR.mkdir(exist_ok=True)

LOW = 70
HIGH = 180
VERY_LOW = 54
VERY_HIGH = 250


def _chart_path(target_date: date) -> Path:
    return CHART_DIR / f"glucose_{target_date}.png"


def generate_daily_chart(target_date: date, force: bool = False) -> Optional[Path]:
    """
    Genera el chart AGP del día y lo guarda en charts/glucose_YYYY-MM-DD.png.
    Si el archivo ya existe y no es hoy, lo reutiliza (force=True para regenerar).
    Retorna la ruta del archivo o None si no hay datos.
    """
    path = _chart_path(target_date)

    # Reutilizar si ya existe y no es el día actual
    if path.exists() and target_date != date.today() and not force:
        return path

    df = get_readings_by_date(target_date)
    if df.empty or len(df) < 2:
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/Bogota")
    df = df.sort_values("timestamp")

    metrics = calculate_daily_metrics(df)

    fig, ax = plt.subplots(figsize=(14, 6))

    # ── Zonas de color ─────────────────────────────────────────────────────────
    ax.axhspan(VERY_LOW, LOW,   alpha=0.12, color="#FF6B6B", label="Hipo leve (<70)")
    ax.axhspan(0, VERY_LOW,     alpha=0.20, color="#C0392B", label="Hipo severa (<54)")
    ax.axhspan(HIGH, VERY_HIGH, alpha=0.12, color="#F39C12", label="Hiper leve (>180)")
    ax.axhspan(VERY_HIGH, 420,  alpha=0.18, color="#E74C3C", label="Hiper severa (>250)")
    ax.axhspan(LOW, HIGH,       alpha=0.08, color="#2ECC71", label="En rango (70-180)")

    # ── Líneas de umbral ───────────────────────────────────────────────────────
    ax.axhline(LOW,       color="#E74C3C", linestyle="--", linewidth=1.3, alpha=0.75)
    ax.axhline(HIGH,      color="#E74C3C", linestyle="--", linewidth=1.3, alpha=0.75)
    ax.axhline(VERY_LOW,  color="#8E44AD", linestyle=":", linewidth=1.1, alpha=0.65)
    ax.axhline(VERY_HIGH, color="#8E44AD", linestyle=":", linewidth=1.1, alpha=0.65)

    # Etiquetas de umbrales
    ax.text(df["timestamp"].max(), LOW + 2,       "70", color="#E74C3C", fontsize=8, va="bottom")
    ax.text(df["timestamp"].max(), HIGH + 2,      "180", color="#E74C3C", fontsize=8, va="bottom")

    # ── Línea de glucosa ──────────────────────────────────────────────────────
    ax.plot(
        df["timestamp"], df["glucose_mgdl"],
        color="#2C3E50", linewidth=2.2, marker="o", markersize=4.5, zorder=5,
        label="Glucosa"
    )

    # ── Formato ejes ──────────────────────────────────────────────────────────
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.xticks(rotation=45, fontsize=9)
    ax.set_ylim(0, max(380, float(df["glucose_mgdl"].max()) + 40))
    ax.set_xlabel("Hora del día", fontsize=11)
    ax.set_ylabel("Glucosa (mg/dL)", fontsize=11)
    ax.grid(True, alpha=0.25, linestyle="--")

    # ── Título con métricas AGP ───────────────────────────────────────────────
    if metrics:
        title = (
            f"Perfil glucémico  —  {target_date.strftime('%d de %B de %Y')}\n"
            f"TIR {metrics['tir_percent']}%  •  "
            f"Promedio {metrics['avg_glucose']} mg/dL  •  "
            f"CV {metrics['cv_percent']}%  •  "
            f"GMI {metrics['gmi_percent']}%  •  "
            f"Lecturas: {metrics['reading_count']}"
        )
    else:
        title = f"Perfil glucémico — {target_date.strftime('%d de %B de %Y')}"

    ax.set_title(title, fontsize=11, fontweight="bold", pad=12)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.75, ncol=3)

    plt.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

    return path


def chart_to_base64(target_date: date) -> Optional[str]:
    """
    Genera (o reutiliza) el chart del día y lo retorna como string base64.
    Usado por el dashboard Streamlit.
    """
    path = generate_daily_chart(target_date)
    if path is None or not path.exists():
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
