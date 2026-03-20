"""
Página 4 — Informe Médico.
Resumen clínico para llevar a la consulta. LLM en Fase 4.
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
    page_title="Informe Médico | Glucose Intelligence",
    page_icon="📋",
    layout="wide",
)

with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    online = api.is_api_online()
    api_status_banner(online)

st.title("📋 Informe Médico")
st.caption("Resumen clínico para llevar a la consulta con el endocrinólogo")

if not online:
    st.error("API no disponible.")
    st.stop()

# ─── Período ──────────────────────────────────────────────────────────────────
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
    st.warning("No hay datos en el período seleccionado.")
    st.stop()

# ─── Resumen estadístico del período ─────────────────────────────────────────
st.subheader(f"Resumen del período ({len(period_dates)} días con datos)")

summaries = [api.get_daily_summary(date.fromisoformat(d)) for d in period_dates]
summaries = [s for s in summaries if s]

if summaries:
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
        st.metric(f"{gmi_icon} GMI del período", f"{gmi:.2f}%", delta="HbA1c estimada")
    with col4:
        st.metric("⚡ Total episodios", f"Hipo {total_hypo} | Hiper {total_hyper}")

    st.divider()

    # ─── Tabla de días ─────────────────────────────────────────────────────────
    st.subheader("Detalle por día")
    df_show = df[["date","reading_count","avg_glucose_mgdl","tir_percent",
                  "tar_percent","tbr_percent","cv_percent","gmi_percent",
                  "hypo_episodes","hyper_episodes"]].copy()
    df_show.columns = ["Fecha","Lecturas","Prom mg/dL","TIR%","TAR%",
                        "TBR%","CV%","GMI%","Hipoglucemias","Hiperglucemias"]

    def _color_tir(v: float) -> str:
        return ("background-color:#d4edda" if v >= 70
                else "background-color:#fff3cd" if v >= 50
                else "background-color:#f8d7da")

    st.dataframe(
        df_show.style
        .applymap(_color_tir, subset=["TIR%"])
        .format({"Prom mg/dL":"{:.1f}","TIR%":"{:.1f}","TAR%":"{:.1f}",
                 "TBR%":"{:.1f}","CV%":"{:.1f}","GMI%":"{:.2f}"}),
        use_container_width=True, hide_index=True,
    )

    st.divider()

    # ─── Puntos para llevar al médico ─────────────────────────────────────────
    st.subheader("📌 Puntos para la consulta médica")

    puntos = []
    if avg_tir < 70:
        puntos.append(f"TIR promedio **{avg_tir:.1f}%** — por debajo del objetivo del 70%. Preguntar sobre ajuste de dosis.")
    if avg_cv > 36:
        puntos.append(f"CV **{avg_cv:.1f}%** — glucosa muy variable. Puede indicar dosis de rápida incorrecta o falta de conteo de carbohidratos.")
    if total_hypo > 2:
        puntos.append(f"**{total_hypo} episodios** de hipoglucemia en el período. Revisar si la dosis basal o correcciones son excesivas.")
    if avg_tar > 25:
        puntos.append(f"TAR promedio **{avg_tar:.1f}%** — mucho tiempo con glucosa alta. Revisar insulina prandial y dieta.")
    if gmi > 7.5:
        puntos.append(f"GMI **{gmi:.2f}%** — HbA1c estimada por encima del objetivo. Considerar ajuste del esquema.")

    if puntos:
        for p in puntos:
            st.markdown(f"- {p}")
    else:
        st.success("¡Buen control en el período! Continuar con el esquema actual.")

    st.divider()

    # ─── IA (próxima fase) ────────────────────────────────────────────────────
    st.subheader("🤖 Interpretación con IA")
    st.info(
        "**Próximamente — Fase 4:** Azure OpenAI analizará estos datos con el "
        "perfil clínico de la paciente (medicamentos, historial) y generará "
        "un informe médico personalizado en lenguaje natural, listo para llevar al médico.",
        icon="🧠",
    )
    st.caption("Configurar `AZURE_OPENAI_API_KEY` en el `.env` para activar esta función.")
