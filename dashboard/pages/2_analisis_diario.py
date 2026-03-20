"""
Página: Análisis Diario.
Chart AGP del día + métricas clínicas TIR/TAR/TBR/CV.
UN SOLO chart por día (no uno por ejecución).
"""

import streamlit as st
from datetime import date, timedelta

st.set_page_config(page_title="Análisis Diario | Glucose Intelligence", layout="wide")

st.title("📊 Análisis Diario")

# ─── Selector de fecha ─────────────────────────────────────────────────────────
selected_date = st.date_input(
    "Seleccionar día",
    value=date.today(),
    max_value=date.today(),
    min_value=date.today() - timedelta(days=90),
)

st.divider()

# ─── Métricas AGP del día ──────────────────────────────────────────────────────
st.subheader("Métricas Clínicas (AGP)")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label="✅ TIR",
        value="—%",
        delta="objetivo: >70%",
        help="Time In Range: % del tiempo con glucosa 70-180 mg/dL"
    )
with col2:
    st.metric(
        label="🔴 TAR",
        value="—%",
        delta="objetivo: <25%",
        help="Time Above Range: % del tiempo con glucosa >180 mg/dL"
    )
with col3:
    st.metric(
        label="🟡 TBR",
        value="—%",
        delta="objetivo: <4%",
        help="Time Below Range: % del tiempo con glucosa <70 mg/dL"
    )
with col4:
    st.metric(
        label="📈 eA1C",
        value="—%",
        delta="HbA1c estimada",
        help="Glucose Management Indicator: estima HbA1c desde CGM"
    )
with col5:
    st.metric(
        label="📉 CV%",
        value="—%",
        delta="objetivo: <36%",
        help="Coeficiente de variación: indica estabilidad glucémica"
    )

st.divider()

# ─── Chart AGP del día ─────────────────────────────────────────────────────────
st.subheader(f"Perfil Glucémico — {selected_date.strftime('%d %B %Y')}")
st.info("TODO: Chart AGP interactivo con Plotly — GET /api/summaries/chart/daily/{date}")

st.markdown("""
**El chart mostrará:**
- Línea de glucosa con puntos de lectura
- Zonas de color: verde (rango), amarillo (límites), rojo (crítico)
- Líneas de umbral (70, 180, 55, 250 mg/dL)
- Anotación de episodios hipoglucémicos/hiperglucémicos
- Zona nocturna sombreada (00:00–06:00)
""")

st.divider()

# ─── Interpretación IA ─────────────────────────────────────────────────────────
st.subheader("🤖 Interpretación Clínica (Azure OpenAI)")
st.info("TODO: GET /api/reports/generate — interpretación del día con contexto del paciente")
st.caption("La IA considera el perfil clínico de la paciente, sus medicamentos y su historial para personalizar el análisis.")
