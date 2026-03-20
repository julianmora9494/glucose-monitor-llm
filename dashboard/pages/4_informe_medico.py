"""
Página: Informe Médico.
Reporte generado por Azure OpenAI para llevar a la consulta médica.
"""

import streamlit as st
from datetime import date, timedelta

st.set_page_config(page_title="Informe Médico | Glucose Intelligence", layout="wide")

st.title("📋 Informe Médico")
st.caption("Reporte clínico generado con IA — para llevar a la consulta con el endocrinólogo")

# ─── Configuración del informe ─────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    date_from = st.date_input(
        "Desde",
        value=date.today() - timedelta(days=14),
        max_value=date.today(),
    )
with col2:
    date_to = st.date_input(
        "Hasta",
        value=date.today(),
        max_value=date.today(),
    )
with col3:
    include_recommendations = st.checkbox("Incluir recomendaciones", value=True)

generate_btn = st.button("🤖 Generar Informe con IA", type="primary", use_container_width=True)

st.divider()

if generate_btn:
    with st.spinner("Analizando datos glucémicos con Azure OpenAI..."):
        # TODO: llamar POST /api/reports/generate
        st.info("TODO: implementar llamada a la API")
else:
    # ─── Preview de la estructura del informe ─────────────────────────────────
    st.subheader("Estructura del informe")

    with st.expander("📊 Resumen Ejecutivo", expanded=True):
        st.markdown("""
        *Aquí aparecerá el resumen del período analizado en lenguaje médico accesible,
        con las métricas AGP principales y una evaluación general del control glucémico.*
        """)

    with st.expander("🔍 Análisis del Control Glucémico"):
        st.markdown("""
        *Análisis detallado: TIR, TAR, TBR, CV%, GMI/eA1C, MAGE.
        Comparación con objetivos glucémicos acordados.*
        """)

    with st.expander("🧩 Patrones Clínicos Detectados"):
        st.markdown("""
        *Patrones identificados por IA: fenómeno del amanecer, hipoglucemias nocturnas,
        picos post-prandiales, días con mal control, variabilidad por día de la semana.*
        """)

    with st.expander("💊 Recomendaciones Personalizadas"):
        st.markdown("""
        *Recomendaciones basadas en los patrones detectados y el perfil clínico de la paciente.
        Considera medicamentos actuales, comorbilidades y objetivos del médico tratante.*
        """)

    with st.expander("👨‍⚕️ Sección Técnica para el Médico"):
        st.markdown("""
        *Informe técnico en lenguaje médico especializado para el endocrinólogo.
        Incluye tablas de datos, análisis estadístico y sugerencias terapéuticas.*
        """)

st.divider()

# ─── Exportar PDF ─────────────────────────────────────────────────────────────
st.subheader("📄 Exportar PDF")
st.info("TODO: Botón para descargar el informe como PDF formato AGP — GET /api/reports/pdf/{date}")
st.caption("El PDF seguirá el formato estándar AGP (Ambulatory Glucose Profile) compatible con cualquier endocrinólogo.")
