"""
Componentes visuales reutilizables del dashboard.
Métricas AGP, charts Plotly y tarjetas de estado.
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Umbrales
VERY_LOW, LOW, HIGH, VERY_HIGH = 54, 70, 180, 250

# Colores por zona — alpha moderado para que sean visibles sobre fondo oscuro
COLOR_VERY_LOW  = "rgba(220, 53,  69,  0.35)"
COLOR_LOW       = "rgba(255, 140,  0,  0.25)"
COLOR_IN_RANGE  = "rgba(40,  167, 69,  0.20)"
COLOR_HIGH      = "rgba(255, 140,  0,  0.25)"
COLOR_VERY_HIGH = "rgba(220, 53,  69,  0.35)"

GLUCOSE_LINE    = "#00D4FF"          # cian brillante — visible sobre fondo oscuro
THRESHOLD_COLOR = "#FF6B6B"
THRESHOLD_STYLE = dict(color=THRESHOLD_COLOR, width=1.5, dash="dash")


# ─── Tarjeta de glucosa actual ─────────────────────────────────────────────────

def glucose_gauge(reading: dict) -> None:
    """Muestra la glucosa actual como métrica grande con color según rango."""
    glucose = reading["glucose_mgdl"]
    range_type = reading.get("range_type", "normal")
    trend_desc = reading.get("trend_description", "—")
    minutes_ago = reading.get("minutes_ago", 0)
    alert_level = reading.get("alert_level", "ok")

    color_map = {
        "ok":       ("🟢", "normal"),
        "warning":  ("🟡", "inverse"),
        "critical": ("🔴", "inverse"),
    }
    icon, delta_color = color_map.get(alert_level, ("⚪", "off"))

    range_labels = {
        "very_low": "🆘 Hipoglucemia severa",
        "low":      "🚨 Hipoglucemia",
        "normal":   "✅ En rango",
        "high":     "⚠️ Hiperglucemia",
        "very_high":"🆘 Hiperglucemia severa",
    }
    range_label = range_labels.get(range_type, "—")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.metric(
            label=f"{icon} Glucosa actual",
            value=f"{glucose:.0f} mg/dL",
            delta=f"{trend_desc}",
            delta_color=delta_color,
        )
        st.caption(f"{range_label}  •  Hace {minutes_ago:.0f} min")
    with col2:
        slope = reading.get("slope_mgdl_min")
        st.metric("Velocidad", f"{slope:+.1f} mg/min" if slope else "—")
    with col3:
        delta = reading.get("delta_mgdl")
        st.metric("Cambio", f"{delta:+.0f} mg/dL" if delta else "—")


# ─── Mini-chart (últimas horas) ────────────────────────────────────────────────

def mini_chart(readings: list[dict], title: str = "Últimas horas") -> None:
    """Chart de línea compacto con zonas de color."""
    if not readings:
        st.info("Sin datos recientes disponibles.")
        return

    df = pd.DataFrame(readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    fig = _base_glucose_figure(df, title=title, height=300)
    st.plotly_chart(fig, use_container_width=True)


# ─── Chart AGP diario completo ─────────────────────────────────────────────────

def daily_chart(readings: list[dict], summary: Optional[dict], day: str) -> None:
    """Chart AGP interactivo con zonas de color y métricas en el título."""
    if not readings:
        st.warning("Sin datos para este día.")
        return

    df = pd.DataFrame(readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    if summary:
        title = (
            f"Perfil glucémico — {day}  |  "
            f"TIR {summary['tir_percent']}%  •  "
            f"Prom {summary['avg_glucose_mgdl']} mg/dL  •  "
            f"CV {summary['cv_percent']}%  •  "
            f"GMI {summary['gmi_percent']}%"
        )
    else:
        title = f"Perfil glucémico — {day}"

    fig = _base_glucose_figure(df, title=title, height=420)
    st.plotly_chart(fig, use_container_width=True)


def _base_glucose_figure(df: pd.DataFrame, title: str, height: int = 400) -> go.Figure:
    """Figura Plotly base con línea de glucosa + zonas de color + umbrales."""
    y_max = max(380, float(df["glucose_mgdl"].max()) + 40)

    fig = go.Figure()

    # Zonas de color (orden: de fondo a frente)
    _add_zone(fig, 0,          VERY_LOW, COLOR_VERY_LOW,  "Hipo severa (<54)",  df)
    _add_zone(fig, VERY_LOW,   LOW,      COLOR_LOW,        "Hipo (<70)",         df)
    _add_zone(fig, LOW,        HIGH,     COLOR_IN_RANGE,   "En rango (70-180)",  df)
    _add_zone(fig, HIGH,       VERY_HIGH,COLOR_HIGH,       "Hiper (>180)",       df)
    _add_zone(fig, VERY_HIGH,  y_max,    COLOR_VERY_HIGH,  "Hiper severa (>250)",df)

    # Líneas de umbral
    for y in (LOW, HIGH):
        fig.add_hline(y=y, line=THRESHOLD_STYLE, opacity=0.7)
    for y in (VERY_LOW, VERY_HIGH):
        fig.add_hline(y=y, line=dict(color="#8E44AD", width=1, dash="dot"), opacity=0.6)

    # Línea de glucosa — cian brillante, gruesa, visible sobre fondo oscuro
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["glucose_mgdl"],
        mode="lines+markers",
        name="Glucosa",
        line=dict(color=GLUCOSE_LINE, width=3),
        marker=dict(size=6, color=GLUCOSE_LINE, line=dict(color="white", width=1)),
        hovertemplate="<b>%{y:.0f} mg/dL</b><br>%{x|%H:%M}<extra></extra>",
        zorder=10,
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#e0e0e0")),
        height=height,
        xaxis=dict(title="Hora", tickformat="%H:%M",
                   gridcolor="#2a2a2a", color="#b0b0b0", title_font=dict(color="#b0b0b0")),
        yaxis=dict(title="Glucosa (mg/dL)", range=[0, y_max],
                   gridcolor="#2a2a2a", color="#b0b0b0", title_font=dict(color="#b0b0b0")),
        plot_bgcolor="#141414",
        paper_bgcolor="#141414",
        font=dict(color="#e0e0e0"),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
            bgcolor="rgba(20,20,20,0.9)", font=dict(color="#e0e0e0"), borderwidth=0,
        ),
        margin=dict(l=50, r=20, t=70, b=50),
        hovermode="x unified",
    )

    return fig


def _add_zone(
    fig: go.Figure, y0: float, y1: float, color: str, name: str, df: pd.DataFrame
) -> None:
    fig.add_trace(go.Scatter(
        x=list(df["timestamp"]) + list(df["timestamp"])[::-1],
        y=[y1] * len(df) + [y0] * len(df),
        fill="toself",
        fillcolor=color,
        line=dict(width=0),
        showlegend=True,
        name=name,
        hoverinfo="skip",
        legendgroup=name,
    ))


# ─── Tarjetas de métricas AGP ─────────────────────────────────────────────────

def agp_metrics_cards(summary: dict) -> None:
    """Muestra las 5 métricas AGP principales como tarjetas con color."""
    status = summary.get("status", {})

    icon_map = {"ok": "✅", "warning": "⚠️", "alert": "🔴"}

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        icon = icon_map.get(status.get("tir", ""), "—")
        st.metric(
            f"{icon} TIR",
            f"{summary['tir_percent']}%",
            delta="objetivo >70%",
            help="Tiempo en Rango: % del día con glucosa entre 70 y 180 mg/dL",
        )
    with col2:
        icon = icon_map.get(status.get("tar", ""), "—")
        st.metric(
            f"{icon} TAR",
            f"{summary['tar_percent']}%",
            delta="objetivo <25%",
            help="Tiempo Sobre Rango: % del día con glucosa por encima de 180 mg/dL",
        )
    with col3:
        icon = icon_map.get(status.get("tbr", ""), "—")
        st.metric(
            f"{icon} TBR",
            f"{summary['tbr_percent']}%",
            delta="objetivo <4%",
            help="Tiempo Bajo Rango: % del día con glucosa por debajo de 70 mg/dL",
        )
    with col4:
        icon = icon_map.get(status.get("cv", ""), "—")
        st.metric(
            f"{icon} CV",
            f"{summary['cv_percent']}%",
            delta="objetivo <36%",
            help="Coeficiente de Variación: qué tan estable estuvo la glucosa",
        )
    with col5:
        icon = icon_map.get(status.get("gmi", ""), "—")
        st.metric(
            f"{icon} GMI",
            f"{summary['gmi_percent']}%",
            delta="HbA1c estimada",
            help="Glucose Management Indicator: estimación de la HbA1c desde el sensor",
        )


def agp_secondary_metrics(summary: dict) -> None:
    """Métricas secundarias: min/max, episodios, MAGE."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📈 Promedio", f"{summary['avg_glucose_mgdl']} mg/dL")
    with col2:
        st.metric(
            "📉 Mín / Máx",
            f"{summary['min_glucose_mgdl']:.0f} / {summary['max_glucose_mgdl']:.0f} mg/dL",
        )
    with col3:
        st.metric(
            "⚡ Episodios",
            f"Hipo: {summary['hypo_episodes']} | Hiper: {summary['hyper_episodes']}",
        )
    with col4:
        mage = summary.get("mage_mgdl")
        st.metric(
            "📊 MAGE",
            f"{mage:.0f} mg/dL" if mage else "—",
            help="Amplitud media de excursiones glucémicas. Objetivo <140 mg/dL",
        )


# ─── Barra de estado de conexión ──────────────────────────────────────────────

def api_status_banner(online: bool) -> None:
    if online:
        st.success("API conectada", icon="🟢")
    else:
        st.error(
            "API no disponible — inicia el backend:\n`uvicorn api.main:app --port 8888 --reload`",
            icon="🔴",
        )
