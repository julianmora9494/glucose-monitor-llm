"""
Página 1 — Tiempo Real.
Glucosa actual con auto-refresh cada 2 minutos.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import dashboard.api_client as api
from dashboard.components import (
    api_status_banner,
    glucose_gauge,
    mini_chart,
)

st.set_page_config(
    page_title="Tiempo Real | Glucose Intelligence",
    page_icon="⏱",
    layout="wide",
)

# Auto-refresh cada 2 minutos (igual que POLL_SECONDS del monitor)
st_autorefresh(interval=120_000, key="realtime_refresh")

with st.sidebar:
    st.title("🩸 Glucose Intelligence")
    online = api.is_api_online()
    api_status_banner(online)

st.title("⏱ Tiempo Real")

if not online:
    st.error("API no disponible. Inicia el backend primero.")
    st.stop()

# ─── Lectura actual ───────────────────────────────────────────────────────────
latest = api.get_latest_reading()

if not latest:
    st.warning("Sin lecturas disponibles. El monitor puede no estar corriendo.")
    st.info("Arranca el monitor: `python monitor/monitor_glucose.py`")
    st.stop()

glucose_gauge(latest)

st.divider()

# ─── Alertas activas ──────────────────────────────────────────────────────────
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

# ─── Mini-chart últimas 3 horas ───────────────────────────────────────────────
st.subheader("Últimas 3 horas")
recent = api.get_readings_last_hours(3)
mini_chart(recent, title="")

# ─── Info de refresh ─────────────────────────────────────────────────────────
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.caption("🔄 Esta página se actualiza automáticamente cada 2 minutos.")
with col2:
    if st.button("↺ Actualizar ahora"):
        st.rerun()
