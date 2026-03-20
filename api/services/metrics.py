"""
Cálculo de métricas clínicas AGP (Ambulatory Glucose Profile).
Estándar internacional para evaluación de control glucémico en CGM.
"""

from datetime import date
from typing import Optional

import numpy as np
import pandas as pd


# Umbrales clínicos estándar ADA/EASD
VERY_LOW = 54    # mg/dL — hipoglucemia severa
LOW = 70         # mg/dL — hipoglucemia
HIGH = 180       # mg/dL — hiperglucemia
VERY_HIGH = 250  # mg/dL — hiperglucemia severa


def calc_tir(glucose_values: pd.Series) -> float:
    """
    Time In Range: % de lecturas entre LOW y HIGH (70-180 mg/dL).
    Objetivo: >70% para la mayoría de pacientes con DM1.
    """
    if len(glucose_values) == 0:
        return 0.0
    return float((glucose_values.between(LOW, HIGH)).mean() * 100)


def calc_tar(glucose_values: pd.Series, threshold: float = HIGH) -> float:
    """
    Time Above Range: % de lecturas por encima del umbral.
    Objetivo: <25% (>180 mg/dL).
    """
    if len(glucose_values) == 0:
        return 0.0
    return float((glucose_values > threshold).mean() * 100)


def calc_tbr(glucose_values: pd.Series, threshold: float = LOW) -> float:
    """
    Time Below Range: % de lecturas por debajo del umbral.
    Objetivo: <4% (<70 mg/dL), <1% (<54 mg/dL severo).
    """
    if len(glucose_values) == 0:
        return 0.0
    return float((glucose_values < threshold).mean() * 100)


def calc_cv(glucose_values: pd.Series) -> float:
    """
    Coeficiente de variación glucémica: (SD / media) × 100.
    Objetivo: <36%. Indicador de estabilidad glucémica.
    Un CV alto indica mayor riesgo de hipoglucemias.
    """
    if len(glucose_values) < 2:
        return 0.0
    mean = glucose_values.mean()
    if mean == 0:
        return 0.0
    return float((glucose_values.std() / mean) * 100)


def calc_gmi(mean_glucose: float) -> float:
    """
    Glucose Management Indicator: estima HbA1c desde glucosa promedio CGM.
    Fórmula ADA 2018: GMI (%) = 3.31 + 0.02392 × mean_glucose_mgdl
    Objetivo: según meta individual del médico (típicamente <7%).
    """
    return round(3.31 + 0.02392 * mean_glucose, 2)


def calc_mage(glucose_values: pd.Series) -> Optional[float]:
    """
    Mean Amplitude of Glycemic Excursions.
    Mide la magnitud de las oscilaciones glucémicas.
    Objetivo: <140 mg/dL.

    Método: promedio de todas las excursiones (picos-valles o valles-picos)
    que superen 1 desviación estándar.
    """
    if len(glucose_values) < 4:
        return None

    values = glucose_values.values
    sd = glucose_values.std()
    excursions = []

    i = 0
    while i < len(values) - 1:
        # Buscar pico local
        if i > 0 and values[i] > values[i - 1] and values[i] > values[i + 1]:
            # Buscar el valle previo más cercano
            j = i - 1
            while j > 0 and values[j] >= values[j - 1]:
                j -= 1
            excursion = abs(values[i] - values[j])
            if excursion > sd:
                excursions.append(excursion)
        # Buscar valle local
        elif i > 0 and values[i] < values[i - 1] and values[i] < values[i + 1]:
            j = i - 1
            while j > 0 and values[j] <= values[j - 1]:
                j -= 1
            excursion = abs(values[j] - values[i])
            if excursion > sd:
                excursions.append(excursion)
        i += 1

    if not excursions:
        return None
    return float(np.mean(excursions))


def count_episodes(
    glucose_values: pd.Series,
    timestamps: pd.Series,
    threshold: float,
    above: bool = False,
    gap_minutes: float = 15.0,
) -> int:
    """
    Cuenta episodios de hipo o hiperglucemia.
    Un episodio termina cuando hay ≥ gap_minutes sin lecturas fuera de rango.
    """
    if len(glucose_values) == 0:
        return 0

    df = pd.DataFrame({"glucose": glucose_values.values, "ts": pd.to_datetime(timestamps.values)})
    df = df.sort_values("ts").reset_index(drop=True)

    if above:
        out_of_range = df["glucose"] > threshold
    else:
        out_of_range = df["glucose"] < threshold

    episodes = 0
    in_episode = False
    last_ts = None

    for _, row in df.iterrows():
        if out_of_range[_]:
            if not in_episode:
                episodes += 1
                in_episode = True
            last_ts = row["ts"]
        else:
            if in_episode and last_ts is not None:
                gap = (row["ts"] - last_ts).total_seconds() / 60
                if gap >= gap_minutes:
                    in_episode = False

    return episodes


def calculate_daily_metrics(df: pd.DataFrame) -> dict:
    """
    Calcula todas las métricas AGP para un DataFrame de lecturas diarias.

    Args:
        df: DataFrame con columnas timestamp, glucose_mgdl (mínimo requerido)

    Returns:
        Diccionario con todas las métricas clínicas del día
    """
    if df.empty:
        return {}

    glucose = df["glucose_mgdl"]
    timestamps = df["timestamp"]

    mean_glucose = float(glucose.mean())
    std_glucose = float(glucose.std()) if len(glucose) > 1 else 0.0

    return {
        "reading_count": len(glucose),
        "avg_glucose": round(mean_glucose, 1),
        "std_glucose": round(std_glucose, 1),
        "cv_percent": round(calc_cv(glucose), 1),
        "tir_percent": round(calc_tir(glucose), 1),
        "tar_percent": round(calc_tar(glucose), 1),
        "tbr_percent": round(calc_tbr(glucose), 1),
        "tbr_severe_percent": round(calc_tbr(glucose, threshold=VERY_LOW), 1),
        "gmi_percent": calc_gmi(mean_glucose),
        "mage_mgdl": round(mage, 1) if (mage := calc_mage(glucose)) else None,
        "hypo_episodes": count_episodes(glucose, timestamps, threshold=LOW, above=False),
        "hyper_episodes": count_episodes(glucose, timestamps, threshold=HIGH, above=True),
        "min_glucose": float(glucose.min()),
        "max_glucose": float(glucose.max()),
    }


def interpret_metrics(metrics: dict) -> dict[str, str]:
    """
    Evalúa cada métrica contra los objetivos clínicos ADA.
    Retorna un diccionario con el status de cada indicador.
    Status: 'ok' | 'warning' | 'alert'
    """
    if not metrics:
        return {}

    return {
        "tir": "ok" if metrics["tir_percent"] >= 70 else (
            "warning" if metrics["tir_percent"] >= 50 else "alert"
        ),
        "tar": "ok" if metrics["tar_percent"] <= 25 else (
            "warning" if metrics["tar_percent"] <= 40 else "alert"
        ),
        "tbr": "ok" if metrics["tbr_percent"] <= 4 else (
            "warning" if metrics["tbr_percent"] <= 8 else "alert"
        ),
        "tbr_severe": "ok" if metrics["tbr_severe_percent"] <= 1 else "alert",
        "cv": "ok" if metrics["cv_percent"] <= 36 else (
            "warning" if metrics["cv_percent"] <= 45 else "alert"
        ),
        "gmi": "ok" if metrics["gmi_percent"] <= 7.0 else (
            "warning" if metrics["gmi_percent"] <= 8.0 else "alert"
        ),
    }


def format_daily_report(metrics: dict, target_date: date) -> str:
    """
    Formatea el resumen diario para enviar por Telegram.
    """
    if not metrics:
        return f"Sin datos suficientes para {target_date}"

    status = interpret_metrics(metrics)

    def icon(key: str) -> str:
        return {"ok": "✅", "warning": "⚠️", "alert": "🔴"}.get(status.get(key, ""), "—")

    lines = [
        f"📊 *Resumen glucémico — {target_date.strftime('%d/%m/%Y')}*",
        f"",
        f"{icon('tir')} TIR: {metrics['tir_percent']}%  _(objetivo >70%)_",
        f"{icon('tar')} TAR: {metrics['tar_percent']}%  _(objetivo <25%)_",
        f"{icon('tbr')} TBR: {metrics['tbr_percent']}%  _(objetivo <4%)_",
        f"{icon('cv')} CV: {metrics['cv_percent']}%  _(objetivo <36%)_",
        f"{icon('gmi')} GMI: {metrics['gmi_percent']}%  _(HbA1c estimada)_",
        f"",
        f"📈 Promedio: {metrics['avg_glucose']} mg/dL",
        f"📉 Mín/Máx: {metrics['min_glucose']:.0f} / {metrics['max_glucose']:.0f} mg/dL",
        f"🔁 Lecturas: {metrics['reading_count']}",
        f"⚡ Episodios hipo: {metrics['hypo_episodes']} | hiper: {metrics['hyper_episodes']}",
    ]

    if metrics.get("mage_mgdl"):
        lines.append(f"📊 MAGE: {metrics['mage_mgdl']} mg/dL  _(objetivo <140)_")

    return "\n".join(lines)
