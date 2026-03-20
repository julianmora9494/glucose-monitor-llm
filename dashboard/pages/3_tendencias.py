"""
Página: Tendencias históricas.
TIR diario, eA1C trending, patrones detectados por IA.
"""

import streamlit as st
from datetime import date

st.set_page_config(page_title="Tendencias | Glucose Intelligence", layout="wide")

st.title("📈 Tendencias y Patrones")

# ─── Selector de período ───────────────────────────────────────────────────────
period = st.selectbox(
    "Período de análisis",
    options=["Última semana (7 días)", "Últimas 2 semanas", "Último mes (30 días)"],
    index=0,
)

st.divider()

# ─── TIR histórico diario ──────────────────────────────────────────────────────
st.subheader("Time In Range — histórico")
st.info("TODO: Barchart diario de TIR con línea de objetivo (70%) — GET /api/summaries/weekly")

# ─── eA1C trending ────────────────────────────────────────────────────────────
st.subheader("HbA1c Estimada (GMI) — trending")
st.info("TODO: Línea de eA1C estimada con banda de confianza")

st.divider()

# ─── Patrones detectados por IA ───────────────────────────────────────────────
st.subheader("🧠 Patrones Clínicos Detectados")

# Ejemplos de lo que el sistema detectará:
with st.expander("¿Qué patrones detecta el sistema?"):
    st.markdown("""
    | Patrón | Descripción clínica |
    |--------|---------------------|
    | **Fenómeno del amanecer** | Hiperglucemia 4-8am sin ingesta nocturna |
    | **Rebote post-hipoglucemia** | Efecto Somogyi: hiperglucemia tras hipo nocturna |
    | **Pico post-prandial** | Spike >60 mg/dL en 45-90 min post-comida (inferido) |
    | **Hipoglucemia nocturna** | Episodios <70 mg/dL entre 00:00-06:00 |
    | **Días con mal control** | Clustering de días con TIR <50% |
    | **Patrón semanal** | Días de la semana con peor/mejor control |
    """)

st.info("TODO: Lista de patrones detectados por Azure OpenAI — GET /api/reports/generate")

st.divider()

# ─── Mejores y peores días ────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("✅ Mejores días")
    st.info("TODO: Top 3 días con mejor TIR del período")

with col2:
    st.subheader("⚠️ Días con más episodios")
    st.info("TODO: Días con más hipoglucemias o hiperglucemias")
