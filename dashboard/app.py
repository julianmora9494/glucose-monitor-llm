"""
Glucose Intelligence Dashboard — Streamlit.
Punto de entrada principal del dashboard de monitoreo clínico.

Ejecutar con:
    streamlit run dashboard/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Glucose Intelligence",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    st.caption("María Verónica López Falla")
    st.divider()
    st.info("Selecciona una sección en el menú de páginas")

# ─── Página principal: resumen rápido ─────────────────────────────────────────
st.title("Panel de Control Glucémico")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="🩸 Glucosa Actual",
        value="— mg/dL",
        delta="Cargando...",
    )

with col2:
    st.metric(
        label="⏱ TIR Hoy",
        value="—%",
        delta="vs ayer",
    )

with col3:
    st.metric(
        label="📊 Promedio 7 días",
        value="— mg/dL",
        delta="eA1C estimada",
    )

with col4:
    st.metric(
        label="🔔 Alertas hoy",
        value="—",
        delta="episodios",
    )

st.divider()
st.info("⚙️ Conecta la API en `.env` para ver datos en tiempo real. Ver `api/` para iniciar el backend.")

st.markdown("""
### Navegación

Usa el menú lateral para acceder a:

| Página | Descripción |
|--------|-------------|
| **Tiempo Real** | Glucosa actual, trend, chart últimas 3h |
| **Análisis Diario** | Chart AGP del día, métricas TIR/TAR/TBR |
| **Tendencias** | Histórico 7/14/30 días, patrones detectados |
| **Informe Médico** | Reporte generado por IA para el médico |
""")
