"""
Página 2 — Análisis Diario.
Chart AGP interactivo del día + métricas clínicas completas.
"""

from datetime import date, timedelta

import streamlit as st

import dashboard.api_client as api
from dashboard.components import (
    agp_metrics_cards,
    agp_secondary_metrics,
    api_status_banner,
    daily_chart,
)

st.set_page_config(
    page_title="Análisis Diario | Glucose Intelligence",
    page_icon="📊",
    layout="wide",
)

with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    online = api.is_api_online()
    api_status_banner(online)

st.title("📊 Análisis Diario")

if not online:
    st.error("API no disponible.")
    st.stop()

# ─── Selector de fecha ────────────────────────────────────────────────────────
available = api.get_available_dates()
col_date, col_nav = st.columns([3, 1])

with col_date:
    if available:
        default = date.fromisoformat(available[0])  # día más reciente
        selected = st.date_input(
            "Seleccionar día",
            value=default,
            max_value=date.today(),
            min_value=date.today() - timedelta(days=90),
        )
    else:
        selected = st.date_input("Seleccionar día", value=date.today())

with col_nav:
    st.write("")
    st.write("")
    if available and len(available) > 1:
        idx = available.index(str(selected)) if str(selected) in available else 0
        col_prev, col_next = st.columns(2)
        with col_prev:
            if idx < len(available) - 1 and st.button("◀ Anterior"):
                selected = date.fromisoformat(available[idx + 1])
                st.rerun()
        with col_next:
            if idx > 0 and st.button("Siguiente ▶"):
                selected = date.fromisoformat(available[idx - 1])
                st.rerun()

st.divider()

# ─── Carga de datos ───────────────────────────────────────────────────────────
with st.spinner("Cargando datos..."):
    readings = api.get_readings_day(selected)
    summary = api.get_daily_summary(selected)

if not readings:
    st.warning(f"Sin datos para el {selected.strftime('%d/%m/%Y')}.")
    if available:
        st.info(f"Días con datos: {', '.join(available)}")
    st.stop()

# ─── Métricas AGP ─────────────────────────────────────────────────────────────
st.subheader(f"Métricas clínicas — {selected.strftime('%d de %B de %Y')}")

if summary:
    agp_metrics_cards(summary)
    st.write("")
    agp_secondary_metrics(summary)

    # Interpretación rápida
    status = summary.get("status", {})
    alerts = []
    if status.get("tir") == "alert":
        alerts.append(f"TIR muy bajo ({summary['tir_percent']}%) — glucosa poco tiempo en rango")
    if status.get("tar") == "alert":
        alerts.append(f"TAR alto ({summary['tar_percent']}%) — demasiado tiempo con glucosa elevada")
    if status.get("tbr") == "alert":
        alerts.append(f"TBR alto ({summary['tbr_percent']}%) — demasiadas hipoglucemias")
    if status.get("cv") == "alert":
        alerts.append(f"CV alto ({summary['cv_percent']}%) — glucosa muy inestable")

    if alerts:
        with st.expander("⚠️ Puntos de atención del día", expanded=True):
            for a in alerts:
                st.markdown(f"- {a}")
else:
    st.info("Sin suficientes datos para calcular métricas de este día.")

st.divider()

# ─── Chart interactivo ───────────────────────────────────────────────────────
st.subheader("Perfil glucémico del día")
daily_chart(readings, summary, selected.strftime("%d/%m/%Y"))

st.divider()

# ─── Tabla de lecturas (expandible) ──────────────────────────────────────────
with st.expander(f"📋 Ver todas las lecturas del día ({len(readings)})"):
    import pandas as pd
    df = pd.DataFrame(readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%H:%M")
    df = df.rename(columns={
        "timestamp": "Hora",
        "glucose_mgdl": "Glucosa (mg/dL)",
        "trend": "Tendencia",
        "delta_mgdl": "Cambio (mg/dL)",
        "range_type": "Estado",
    })
    # Colorear la columna estado
    def color_estado(val: str) -> str:
        colors = {
            "normal": "background-color: #d4edda",
            "low": "background-color: #fff3cd",
            "very_low": "background-color: #f8d7da",
            "high": "background-color: #fff3cd",
            "very_high": "background-color: #f8d7da",
        }
        return colors.get(val, "")

    show_cols = ["Hora", "Glucosa (mg/dL)", "Cambio (mg/dL)", "Estado"]
    st.dataframe(
        df[show_cols].style.applymap(color_estado, subset=["Estado"]),
        use_container_width=True,
        hide_index=True,
    )
