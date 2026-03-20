"""
Glucose Intelligence Dashboard — página principal.
Ejecutar con: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path para imports de dashboard.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date

import streamlit as st

import dashboard.api_client as api
from dashboard.components import (
    agp_metrics_cards,
    agp_secondary_metrics,
    api_status_banner,
    glucose_gauge,
    mini_chart,
)

st.set_page_config(
    page_title="Glucose Intelligence",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    st.caption("Monitoreo glucémico continuo")
    st.divider()
    st.markdown("""
    **Páginas:**
    - 🏠 Inicio (esta página)
    - ⏱ Tiempo Real
    - 📊 Análisis Diario
    - 📈 Tendencias
    - 📋 Informe Médico
    """)
    st.divider()
    online = api.is_api_online()
    api_status_banner(online)

# ─── Encabezado ───────────────────────────────────────────────────────────────
st.title("🩸 Panel de Control Glucémico")
st.caption(f"Actualizado: {date.today().strftime('%d de %B de %Y')}")

if not online:
    st.warning("Inicia el backend para ver los datos en tiempo real.")
    st.code("uvicorn api.main:app --port 8080 --reload")
    st.stop()

# ─── Lectura actual ───────────────────────────────────────────────────────────
st.subheader("Estado actual")
latest = api.get_latest_reading()

if latest:
    glucose_gauge(latest)
else:
    st.warning("Sin lectura disponible. El monitor puede no estar corriendo.")

st.divider()

# ─── Resumen del día de hoy ───────────────────────────────────────────────────
st.subheader(f"Resumen de hoy — {date.today().strftime('%d/%m/%Y')}")

today_summary = api.get_daily_summary(date.today())

if today_summary and today_summary.get("reading_count", 0) >= 3:
    agp_metrics_cards(today_summary)
    st.write("")
    agp_secondary_metrics(today_summary)
else:
    st.info("Aún no hay suficientes datos de hoy (mínimo 3 lecturas). Ve a **Análisis Diario** para ver días anteriores.")

st.divider()

# ─── Mini-chart últimas 3 horas ───────────────────────────────────────────────
st.subheader("Últimas 3 horas")
recent = api.get_readings_last_hours(3)
mini_chart(recent, title="")

# ─── Resumen semanal rápido ───────────────────────────────────────────────────
st.divider()
st.subheader("Semana en cifras")

weekly = api.get_weekly_summary()
if weekly:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("TIR promedio", f"{weekly['avg_tir_percent']}%", help="Objetivo >70%")
    with col2:
        st.metric("Glucosa promedio", f"{weekly['avg_glucose_mgdl']} mg/dL")
    with col3:
        st.metric("GMI semanal", f"{weekly['gmi_percent']}%", help="HbA1c estimada de la semana")
    with col4:
        st.metric(
            "Días con datos",
            f"{weekly['days_with_data']} / 7",
        )
else:
    st.info("Sin datos semanales disponibles.")

st.divider()
st.caption("💡 Usa el menú lateral para navegar entre páginas.")
