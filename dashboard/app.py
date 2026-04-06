"""
Glucose Intelligence Dashboard — pagina principal con tiempo real.
Ejecutar con: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Asegurar que la raiz del proyecto este en sys.path para imports de dashboard.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date

import streamlit as st
from streamlit_autorefresh import st_autorefresh

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

# Auto-refresh cada 2 minutos (igual que POLL_SECONDS del monitor)
st_autorefresh(interval=120_000, key="realtime_refresh")

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    st.caption("Monitoreo glucémico continuo")
    st.divider()
    st.markdown("""
    **Páginas:**
    - 🏠 Inicio + Tiempo Real (esta página)
    - 📊 Análisis Diario
    - 📈 Tendencias
    - 📋 Informe Médico
    """)
    st.divider()
    online = api.is_api_online()
    api_status_banner(online)

    # ─── Importar datos ────────────────────────────────────────────────────
    st.divider()
    st.markdown("**Datos**")

    # Estado actual de la DB
    db_status = api.get_db_status() if online else None
    if db_status:
        st.caption(
            f"Última lectura: "
            f"{str(db_status.get('ultima_lectura', '—'))[:16].replace('T', ' ')}"
        )

    # Botón para importar CSVs de Examenes_resultados/ sin reiniciar
    if online and st.button("Importar CSVs", help="Reimporta todos los archivos de Examenes_resultados/", use_container_width=True):
        with st.spinner("Importando datos..."):
            result = api.trigger_csv_import()
        if result:
            n = result.get("total_inserted", 0)
            files = result.get("files_processed", 0)
            if n > 0:
                st.success(f"{n} lecturas nuevas importadas ({files} archivos)")
                st.rerun()
            else:
                st.info(f"Sin datos nuevos en {files} archivo(s) — todo ya estaba importado")

# ─── Encabezado ───────────────────────────────────────────────────────────────
st.title("🩸 Panel de Control Glucémico")
st.caption(f"Actualizado: {date.today().strftime('%d de %B de %Y')}")

if not online:
    st.warning("Inicia el backend para ver los datos en tiempo real.")
    st.code("uvicorn api.main:app --port 8888 --reload")
    st.stop()

# ─── Lectura actual ───────────────────────────────────────────────────────────
st.subheader("Estado actual")
latest = api.get_latest_reading()

if not latest:
    st.warning("Sin lecturas disponibles. El monitor puede no estar corriendo.")
    st.info("Arranca el monitor: `python monitor/monitor_glucose.py`")
    st.stop()

glucose_gauge(latest)

st.divider()

# ─── Alertas contextuales ────────────────────────────────────────────────────
alert_level = latest.get("alert_level", "ok")
glucose = latest.get("glucose_mgdl", 0)
minutes_ago = latest.get("minutes_ago", 0)

if minutes_ago > 15:
    st.warning(
        f"⚠️ La última lectura tiene **{minutes_ago:.0f} minutos** de antigüedad. "
        "El sensor puede estar desconectado.",
        icon="📡",
    )
elif alert_level == "critical":
    if glucose < 70:
        st.error(
            f"🆘 **HIPOGLUCEMIA** — {glucose:.0f} mg/dL\n\n"
            "Tomar azúcar de acción rápida (jugo, glucosa, caramelo) de inmediato. "
            "Medir nuevamente en 15 minutos.",
        )
    else:
        st.error(
            f"🆘 **HIPERGLUCEMIA SEVERA** — {glucose:.0f} mg/dL\n\n"
            "Revisar dosis de insulina. Hidratarse bien. Consultar con el médico si persiste.",
        )
elif alert_level == "warning":
    if glucose < 70:
        st.warning(f"🚨 Glucosa baja: {glucose:.0f} mg/dL — Considera una corrección.")
    else:
        st.warning(f"⚠️ Glucosa alta: {glucose:.0f} mg/dL — Revisa si se aplicó la insulina.")
else:
    st.success(f"✅ Glucosa en rango: {glucose:.0f} mg/dL")

st.divider()

# ─── Mini-chart ultimas 3 horas ──────────────────────────────────────────────
st.subheader("Últimas 3 horas")
recent = api.get_readings_last_hours(3)
mini_chart(recent, title="")

# ─── Resumen del dia de hoy ──────────────────────────────────────────────────
st.divider()
st.subheader(f"Resumen de hoy — {date.today().strftime('%d/%m/%Y')}")

today_summary = api.get_daily_summary(date.today())

if today_summary and today_summary.get("reading_count", 0) >= 3:
    agp_metrics_cards(today_summary)
    st.write("")
    agp_secondary_metrics(today_summary)
else:
    st.info("Aún no hay suficientes datos de hoy (mínimo 3 lecturas). Ve a **Análisis Diario** para ver días anteriores.")

# ─── Resumen semanal rapido ──────────────────────────────────────────────────
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

# ─── Footer ──────────────────────────────────────────────────────────────────
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.caption("🔄 Esta página se actualiza automáticamente cada 2 minutos.")
with col2:
    if st.button("↺ Actualizar ahora"):
        st.rerun()
