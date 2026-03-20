# Glucose Intelligence Platform

> Sistema inteligente de monitoreo glucémico continuo con IA médica, alertas en tiempo real y dashboard clínico.

**Paciente**: María Verónica López Falla — FreeStyle Libre via LibreLinkUp
**Stack**: Python · FastAPI · Streamlit · Azure OpenAI · DuckDB · Telegram

---

## Arquitectura

```
LibreLinkUp API
      │
      ▼
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Monitor   │─────▶│   FastAPI + DB   │─────▶│  Streamlit UI   │
│  Service    │      │   (DuckDB)       │      │  (Dashboard)    │
└─────────────┘      └────────┬─────────┘      └─────────────────┘
                              │
                    ┌─────────┴──────────┐
                    │                    │
              ┌─────▼──────┐    ┌────────▼───────┐
              │  Telegram  │    │  Azure OpenAI  │
              │    Bot     │    │  (LLM médico)  │
              └────────────┘    └────────────────┘
```

## Módulos

| Módulo | Descripción | Estado |
|--------|-------------|--------|
| `monitor/` | Servicio de polling CGM + alertas Telegram | ✅ Producción |
| `api/` | FastAPI backend con métricas AGP | 🚧 En desarrollo |
| `dashboard/` | Streamlit: tiempo real + análisis clínico | 🚧 En desarrollo |
| `llm/` | Interpretaciones con Azure OpenAI | 🚧 En desarrollo |
| `clinical_history/` | Historial clínico de la paciente | 📋 Ver instrucciones |

---

## Instalación rápida

```bash
# 1. Clonar el repo
git clone https://github.com/julianmora9494/glucose-monitor-llm.git
cd glucose-monitor-llm

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 4. Instalar dependencias del monitor
pip install -r monitor/requirements.txt

# 5. Ejecutar monitor
python monitor/monitor_glucose.py
```

---

## Branches

| Branch | Propósito |
|--------|-----------|
| `main` | Código estable en producción |
| `feature/llm-platform` | Nueva plataforma con LLM, FastAPI, Streamlit |

---

## Historial clínico

Ver instrucciones en [clinical_history/README.md](clinical_history/README.md) para cargar el historial de ChatGPT y exámenes de laboratorio.

---

## Métricas clínicas que calcula el sistema

| Métrica | Descripción | Objetivo |
|---------|-------------|---------|
| **TIR** | Time In Range (70–180 mg/dL) | >70% |
| **TAR** | Time Above Range (>180 mg/dL) | <25% |
| **TBR** | Time Below Range (<70 mg/dL) | <4% |
| **CV%** | Coeficiente de variación glucémica | <36% |
| **eA1C** | HbA1c estimada por CGM | Según objetivo del médico |
| **GMI** | Glucose Management Indicator | Según objetivo del médico |
| **MAGE** | Mean Amplitude of Glycemic Excursions | <140 mg/dL |
