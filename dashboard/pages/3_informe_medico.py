"""
Pagina 4 — Informe Medico con IA.
Resumen clinico para llevar a la consulta. Integra Azure OpenAI (Fase 4).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import dashboard.api_client as api
from dashboard.components import agp_metrics_cards, api_status_banner

st.set_page_config(
    page_title="Informe Medico | Glucose Intelligence",
    page_icon="📋",
    layout="wide",
)

with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    online = api.is_api_online()
    api_status_banner(online)

st.title("📋 Informe Medico")
st.caption("Resumen clinico para llevar a la consulta con el endocrinologo")

if not online:
    st.error("API no disponible.")
    st.stop()

# ─── Periodo ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    date_from = st.date_input("Desde", value=date.today() - timedelta(days=13))
with col2:
    date_to = st.date_input("Hasta", value=date.today())

st.divider()

# ─── Datos disponibles ────────────────────────────────────────────────────────
available = api.get_available_dates()
period_dates = [d for d in available if str(date_from) <= d <= str(date_to)]

if not period_dates:
    st.warning("No hay datos en el periodo seleccionado.")
    st.stop()

# ─── Resumen estadistico del periodo ─────────────────────────────────────────
st.subheader(f"Resumen del periodo ({len(period_dates)} dias con datos)")

summaries = [api.get_daily_summary(date.fromisoformat(d)) for d in period_dates]
summaries = [s for s in summaries if s]

if not summaries:
    st.warning("No se pudieron obtener metricas del periodo.")
    st.stop()

df = pd.DataFrame(summaries)

avg_tir  = df["tir_percent"].mean()
avg_tar  = df["tar_percent"].mean()
avg_tbr  = df["tbr_percent"].mean()
avg_cv   = df["cv_percent"].mean()
avg_gluc = df["avg_glucose_mgdl"].mean()
gmi      = 3.31 + 0.02392 * avg_gluc
total_hypo  = int(df["hypo_episodes"].sum())
total_hyper = int(df["hyper_episodes"].sum())

col1, col2, col3, col4 = st.columns(4)
with col1:
    tir_icon = "✅" if avg_tir >= 70 else ("⚠️" if avg_tir >= 50 else "🔴")
    st.metric(f"{tir_icon} TIR promedio", f"{avg_tir:.1f}%", delta="objetivo >70%")
with col2:
    cv_icon = "✅" if avg_cv <= 36 else ("⚠️" if avg_cv <= 45 else "🔴")
    st.metric(f"{cv_icon} CV promedio", f"{avg_cv:.1f}%", delta="objetivo <36%")
with col3:
    gmi_icon = "✅" if gmi <= 7.0 else ("⚠️" if gmi <= 8.0 else "🔴")
    st.metric(f"{gmi_icon} GMI del periodo", f"{gmi:.2f}%", delta="HbA1c estimada")
with col4:
    st.metric("⚡ Total episodios", f"Hipo {total_hypo} | Hiper {total_hyper}")

st.divider()

# ─── Tabla de dias ────────────────────────────────────────────────────────────
st.subheader("Detalle por dia")
df_show = df[["date","reading_count","avg_glucose_mgdl","tir_percent",
              "tar_percent","tbr_percent","cv_percent","gmi_percent",
              "hypo_episodes","hyper_episodes"]].copy()
df_show.columns = ["Fecha","Lecturas","Prom mg/dL","TIR%","TAR%",
                    "TBR%","CV%","GMI%","Hipoglucemias","Hiperglucemias"]

def _color_tir(v: float) -> str:
    if v >= 70: return "background-color: #1b5e20; color: #a5d6a7"
    if v >= 50: return "background-color: #e65100; color: #ffcc80"
    return "background-color: #b71c1c; color: #ef9a9a"

def _color_cv(v: float) -> str:
    if v <= 36: return "background-color: #1b5e20; color: #a5d6a7"
    if v <= 45: return "background-color: #e65100; color: #ffcc80"
    return "background-color: #b71c1c; color: #ef9a9a"

st.dataframe(
    df_show.style
    .applymap(_color_tir, subset=["TIR%"])
    .applymap(_color_cv, subset=["CV%"])
    .format({"Prom mg/dL":"{:.1f}","TIR%":"{:.1f}","TAR%":"{:.1f}",
             "TBR%":"{:.1f}","CV%":"{:.1f}","GMI%":"{:.2f}"}),
    use_container_width=True, hide_index=True,
)

st.divider()

# ─── Puntos para llevar al medico (reglas estaticas) ─────────────────────────
st.subheader("📌 Puntos para la consulta medica")

puntos: list[str] = []
if avg_tir < 70:
    puntos.append(f"TIR promedio **{avg_tir:.1f}%** — por debajo del objetivo del 70%. Preguntar sobre ajuste de dosis.")
if avg_cv > 36:
    puntos.append(f"CV **{avg_cv:.1f}%** — glucosa muy variable. Puede indicar dosis de rapida incorrecta o falta de conteo de carbohidratos.")
if total_hypo > 2:
    puntos.append(f"**{total_hypo} episodios** de hipoglucemia en el periodo. Revisar si la dosis basal o correcciones son excesivas.")
if avg_tar > 25:
    puntos.append(f"TAR promedio **{avg_tar:.1f}%** — mucho tiempo con glucosa alta. Revisar insulina prandial y dieta.")
if gmi > 7.5:
    puntos.append(f"GMI **{gmi:.2f}%** — HbA1c estimada por encima del objetivo. Considerar ajuste del esquema.")

if puntos:
    for p in puntos:
        st.markdown(f"- {p}")
else:
    st.success("Buen control en el periodo. Continuar con el esquema actual.")

st.divider()

# ─── Interpretacion con IA (Azure OpenAI) ───────────────────────────────────
st.subheader("🤖 Interpretacion con IA")

llm_configured = api.is_llm_configured()

if not llm_configured:
    st.info(
        "**Azure OpenAI no configurado.** Agrega `AZURE_OPENAI_API_KEY` y "
        "`AZURE_OPENAI_ENDPOINT` al archivo `.env` para activar el analisis con IA.",
        icon="🔑",
    )
else:
    st.caption("Azure OpenAI conectado — el analisis puede tardar unos segundos.")

    if st.button("🧠 Generar informe con IA", type="primary", use_container_width=True):
        with st.spinner("Analizando datos con Azure OpenAI..."):
            report = api.generate_medical_report(
                date_from=date_from,
                date_to=date_to,
                include_recommendations=True,
            )

        if report:
            # Resumen ejecutivo
            st.markdown("### Resumen ejecutivo")
            st.markdown(report.get("executive_summary", ""))

            # Control glucemico
            st.markdown("### Control glucemico")
            st.markdown(report.get("glycemic_control", ""))

            # Patrones detectados
            patterns = report.get("patterns_detected", [])
            if patterns:
                st.markdown("### Patrones detectados")
                for pattern in patterns:
                    st.markdown(f"- {pattern}")

            # Recomendaciones
            recs = report.get("recommendations", [])
            if recs:
                st.markdown("### Recomendaciones")
                for rec in recs:
                    st.markdown(f"- {rec}")

            # Seccion para el medico
            physician_section = report.get("for_physician", "")
            if physician_section:
                with st.expander("📄 Seccion tecnica para el medico", expanded=False):
                    st.markdown(physician_section)

            st.caption(f"Generado: {report.get('generated_at', '')}")
        else:
            st.error("No se pudo generar el informe. Verificar la conexion con Azure OpenAI.")

    # ─── Chat con IA ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("💬 Preguntale a la IA")
    st.caption(
        "Hazle preguntas sobre la paciente, sus datos glucemicos, medicamentos, "
        "examenes o cualquier duda clinica. La IA tiene acceso al perfil completo "
        "y a todo el historial del CGM."
    )

    # Inicializar historial de chat en session state
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Mostrar historial de conversacion
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input de pregunta
    if question := st.chat_input("Escribe tu pregunta aqui..."):
        # Mostrar pregunta del usuario
        with st.chat_message("user"):
            st.markdown(question)

        # Llamar a la API con historial
        with st.chat_message("assistant"):
            with st.spinner("Analizando..."):
                response = api.chat_with_ai(
                    question=question,
                    conversation_history=st.session_state.chat_messages,
                )

            if response and response.get("answer"):
                answer = response["answer"]
                st.markdown(answer)

                # Guardar en historial
                st.session_state.chat_messages.append({"role": "user", "content": question})
                st.session_state.chat_messages.append({"role": "assistant", "content": answer})
            else:
                st.error("No se pudo obtener respuesta. Verifica la conexion con Azure OpenAI.")

    # Boton para limpiar chat
    if st.session_state.chat_messages:
        if st.button("🗑️ Limpiar conversacion"):
            st.session_state.chat_messages = []
            st.rerun()
