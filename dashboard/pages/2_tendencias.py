"""
Página 3 — Tendencias.
TIR histórico diario, métricas de la semana y comparativa de días.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import dashboard.api_client as api
from dashboard.components import api_status_banner

st.set_page_config(
    page_title="Tendencias | Glucose Intelligence",
    page_icon="📈",
    layout="wide",
)

with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    online = api.is_api_online()
    api_status_banner(online)

st.title("📈 Tendencias y Progreso")

if not online:
    st.error("API no disponible.")
    st.stop()

# ─── Resumen semanal ──────────────────────────────────────────────────────────
weekly = api.get_weekly_summary()

if not weekly or not weekly.get("days"):
    st.warning("Sin datos semanales disponibles. El monitor necesita al menos 1 día de datos.")
    st.stop()

days = weekly["days"]

# ─── KPIs semanales ───────────────────────────────────────────────────────────
st.subheader(f"Semana {weekly['week_start']} — {weekly['week_end']}")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    tir = weekly["avg_tir_percent"]
    icon = "✅" if tir >= 70 else ("⚠️" if tir >= 50 else "🔴")
    st.metric(f"{icon} TIR promedio", f"{tir}%", delta="objetivo >70%")
with col2:
    cv = weekly["avg_cv_percent"]
    icon = "✅" if cv <= 36 else ("⚠️" if cv <= 45 else "🔴")
    st.metric(f"{icon} CV promedio", f"{cv}%", delta="objetivo <36%")
with col3:
    gmi = weekly["gmi_percent"]
    icon = "✅" if gmi <= 7.0 else ("⚠️" if gmi <= 8.0 else "🔴")
    st.metric(f"{icon} GMI semanal", f"{gmi}%", delta="HbA1c estimada")
with col4:
    st.metric("💉 Hipoglucemias", str(weekly["total_hypo_episodes"]), delta="episodios")
with col5:
    st.metric("📈 Hiperglucemias", str(weekly["total_hyper_episodes"]), delta="episodios")

st.divider()

# ─── TIR por día (barras apiladas) ────────────────────────────────────────────
st.subheader("Distribución del tiempo glucémico por día")
st.caption("Cada barra muestra cómo se repartió el día entre rango, hiper e hipo")

df_days = pd.DataFrame(days)

# Barras apiladas: TBR + TIR + TAR
fig_stack = go.Figure()

def _bar_text(series: pd.Series) -> list[str]:
    """Muestra el valor solo si es >= 3%, evita texto en barras muy pequeñas."""
    return [f"{v:.0f}%" if v >= 3 else "" for v in series]

fig_stack.add_bar(
    name="Hipo <70 mg/dL",
    x=df_days["date"], y=df_days["tbr_percent"],
    marker_color="#F39C12",
    text=_bar_text(df_days["tbr_percent"]),
    textposition="inside",
    insidetextfont=dict(color="white", size=13),
)
fig_stack.add_bar(
    name="En rango 70-180",
    x=df_days["date"], y=df_days["tir_percent"],
    marker_color="#2ECC71",
    text=_bar_text(df_days["tir_percent"]),
    textposition="inside",
    insidetextfont=dict(color="white", size=13),
)
fig_stack.add_bar(
    name="Hiper >180 mg/dL",
    x=df_days["date"], y=df_days["tar_percent"],
    marker_color="#E74C3C",
    text=_bar_text(df_days["tar_percent"]),
    textposition="inside",
    insidetextfont=dict(color="white", size=13),
)

fig_stack.add_hline(y=70, line_dash="dash", line_color="#27AE60",
                    annotation_text="objetivo TIR 70%",
                    annotation_font_color="#27AE60")

fig_stack.update_layout(
    barmode="stack",
    height=400,
    yaxis=dict(title="% del día", range=[0, 100], gridcolor="#3a3a3a"),
    xaxis=dict(title="Fecha"),
    plot_bgcolor="#1e1e1e",
    paper_bgcolor="#1e1e1e",
    font=dict(color="#e0e0e0"),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="center", x=0.5,
        bgcolor="rgba(30,30,30,0.8)",
        font=dict(color="#e0e0e0"),
    ),
    margin=dict(l=40, r=20, t=60, b=40),
)
st.plotly_chart(fig_stack, use_container_width=True)

st.divider()

# ─── Glucosa promedio y GMI por día ───────────────────────────────────────────
col_avg, col_cv = st.columns(2)

with col_avg:
    st.subheader("Glucosa promedio por día")
    fig_avg = px.bar(
        df_days, x="date", y="avg_glucose_mgdl",
        color="avg_glucose_mgdl",
        color_continuous_scale=["#2ECC71", "#F39C12", "#E74C3C"],
        range_color=[80, 250],
        labels={"avg_glucose_mgdl": "mg/dL", "date": "Fecha"},
        height=300,
    )
    fig_avg.add_hline(y=154, line_dash="dash", line_color="#27AE60",
                      annotation_text="~GMI 7%")
    fig_avg.update_layout(
        plot_bgcolor="#1e1e1e", paper_bgcolor="#1e1e1e",
        font=dict(color="#e0e0e0"),
        margin=dict(l=40, r=20, t=20, b=40),
        showlegend=False,
    )
    st.plotly_chart(fig_avg, use_container_width=True)

with col_cv:
    st.subheader("Variabilidad (CV%) por día")
    colors = ["#E74C3C" if v > 45 else ("#F39C12" if v > 36 else "#2ECC71")
              for v in df_days["cv_percent"]]
    fig_cv = go.Figure(go.Bar(
        x=df_days["date"], y=df_days["cv_percent"],
        marker_color=colors,
        text=df_days["cv_percent"].apply(lambda x: f"{x:.0f}%"),
        textposition="outside",
    ))
    fig_cv.add_hline(y=36, line_dash="dash", line_color="#27AE60",
                     annotation_text="objetivo <36%")
    fig_cv.update_layout(
        height=300,
        plot_bgcolor="#1e1e1e", paper_bgcolor="#1e1e1e",
        font=dict(color="#e0e0e0"),
        yaxis=dict(title="CV%", gridcolor="#3a3a3a"),
        margin=dict(l=40, r=20, t=20, b=40),
    )
    st.plotly_chart(fig_cv, use_container_width=True)

st.divider()

# ─── Tabla comparativa de días ────────────────────────────────────────────────
st.subheader("Comparativa de días")

display_cols = {
    "date": "Fecha",
    "reading_count": "Lecturas",
    "avg_glucose_mgdl": "Prom (mg/dL)",
    "tir_percent": "TIR%",
    "tar_percent": "TAR%",
    "tbr_percent": "TBR%",
    "cv_percent": "CV%",
    "gmi_percent": "GMI%",
    "hypo_episodes": "Hipoglucemias",
    "hyper_episodes": "Hiperglucemias",
}

df_show = df_days[list(display_cols.keys())].rename(columns=display_cols)


def _color_tir(val: float) -> str:
    # Colores con buen contraste en dark mode
    if val >= 70: return "background-color: #1b5e20; color: #a5d6a7"
    if val >= 50: return "background-color: #e65100; color: #ffcc80"
    return "background-color: #b71c1c; color: #ef9a9a"


def _color_cv(val: float) -> str:
    if val <= 36: return "background-color: #1b5e20; color: #a5d6a7"
    if val <= 45: return "background-color: #e65100; color: #ffcc80"
    return "background-color: #b71c1c; color: #ef9a9a"


def _color_tar(val: float) -> str:
    if val <= 25: return "background-color: #1b5e20; color: #a5d6a7"
    if val <= 40: return "background-color: #e65100; color: #ffcc80"
    return "background-color: #b71c1c; color: #ef9a9a"


def _color_tbr(val: float) -> str:
    if val <= 4: return "background-color: #1b5e20; color: #a5d6a7"
    if val <= 10: return "background-color: #e65100; color: #ffcc80"
    return "background-color: #b71c1c; color: #ef9a9a"


styled = (
    df_show.style
    .applymap(_color_tir, subset=["TIR%"])
    .applymap(_color_tar, subset=["TAR%"])
    .applymap(_color_tbr, subset=["TBR%"])
    .applymap(_color_cv, subset=["CV%"])
    .format({"Prom (mg/dL)": "{:.1f}", "TIR%": "{:.1f}",
             "TAR%": "{:.1f}", "TBR%": "{:.1f}",
             "CV%": "{:.1f}", "GMI%": "{:.2f}"})
)

st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()
st.caption("💡 Con más días de datos aparecerán patrones más claros. Ve a **Informe Médico** para el análisis con IA.")
