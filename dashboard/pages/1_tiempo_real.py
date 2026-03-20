"""
Página: Tiempo Real.
Muestra la glucosa actual con auto-refresh cada 2 minutos.
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Tiempo Real | Glucose Intelligence", layout="wide")

# Auto-refresh cada 2 minutos (igual que el POLL_SECONDS del monitor)
st_autorefresh(interval=120_000, key="realtime_refresh")

st.title("🩸 Monitoreo en Tiempo Real")

# ─── Estado actual ─────────────────────────────────────────────────────────────
col_gauge, col_info = st.columns([1, 2])

with col_gauge:
    st.subheader("Glucosa Actual")
    # TODO: obtener de GET /api/readings/latest
    st.metric(
        label="mg/dL",
        value="— ",
        delta="Tendencia: —",
    )
    st.caption("Actualiza cada 2 minutos")

with col_info:
    st.subheader("Estado clínico")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Hace (min)", "—")
    with col_b:
        st.metric("Cambio", "— mg/dL")
    with col_c:
        st.metric("Velocidad", "— mg/dL·min")

st.divider()

# ─── Chart últimas 3 horas ─────────────────────────────────────────────────────
st.subheader("Últimas 3 horas")
st.info("TODO: Chart interactivo con Plotly — GET /api/readings/range")

st.divider()

# ─── Predicción próximos 30 minutos ───────────────────────────────────────────
st.subheader("🔮 Predicción — próximos 30 min")
pred_col1, pred_col2 = st.columns(2)
with pred_col1:
    st.metric("En 15 minutos", "— mg/dL", delta="confianza: —")
with pred_col2:
    st.metric("En 30 minutos", "— mg/dL", delta="confianza: —")

st.caption("Modelo basado en tendencia de las últimas 4 lecturas")
