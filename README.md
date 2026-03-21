# Glucose Intelligence Platform

> Sistema de monitoreo glucémico continuo con IA médica, alertas en tiempo real y dashboard clínico. Conectado a Abbott FreeStyle Libre via LibreLinkUp.

**Stack:** Python · FastAPI · Streamlit · Azure OpenAI GPT-4o · DuckDB · Telegram
**Repo:** `julianmora9494/glucose-monitor-llm` (privado)

---

## Arquitectura

```
LibreLinkUp API (FreeStyle Libre CGM)
      │
      ▼
monitor/monitor_glucose.py   ← Polling cada 2 min, alertas Telegram
      │
      ▼ POST /api/readings
      │
api/main.py (FastAPI)        ← Único escritor DuckDB (puerto 8888)
      │                          Endpoints: lecturas, métricas AGP, reportes LLM
      │
      ├──► llm/interpreter.py ← Azure OpenAI: interpretación médica
      │
      └──► dashboard/app.py   ← Streamlit: 4 páginas de monitoreo clínico
```

---

## Estado actual por fase

| Fase | Módulo | Estado |
|------|--------|--------|
| 0 | Monitor CGM + alertas Telegram | ✅ Producción (`main`) |
| 1 | DuckDB + métricas AGP + chart diario | ✅ Completo |
| 2 | FastAPI — endpoints de lecturas y resúmenes | ✅ Completo |
| 3 | Streamlit dashboard — 4 páginas clínicas | ✅ Completo |
| 4 | Azure OpenAI — interpretación médica con IA | ✅ Completo |
| 5 | Telegram bot bidireccional + resúmenes diarios | ⏳ Pendiente |
| 6 | Informe médico PDF exportable | ⏳ Pendiente |
| 7 | Predicción glucémica 15–30 min | ⏳ Pendiente |

---

## Instalación

```bash
# 1. Clonar
git clone https://github.com/julianmora9494/glucose-monitor-llm.git
cd glucose-monitor-llm
git checkout feature/llm-platform

# 2. Entorno virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 3. Dependencias
pip install -r requirements.txt

# 4. Variables de entorno
cp .env.example .env
# Editar .env con credenciales reales
```

---

## Inicio rápido

### Importar historial del sensor (una sola vez)
```bash
# Trae hasta ~15 días del FreeStyle Libre a DuckDB
python scripts/import_history.py
```

### Levantar el sistema completo (3 terminales)

**Terminal 1 — FastAPI backend:**
```bash
uvicorn api.main:app --port 8888 --reload
```

**Terminal 2 — Streamlit dashboard:**
```bash
streamlit run dashboard/app.py
```

**Terminal 3 — Monitor CGM (polling continuo):**
```bash
python monitor/monitor_glucose.py
```

El dashboard estará en: `http://localhost:8501`
La API estará en: `http://localhost:8888/docs`

---

## Dashboard — páginas

| Página | Ruta | Descripción |
|--------|------|-------------|
| Inicio | `/` | Glucosa actual + resumen del día + últimas 3h |
| Tiempo Real | `/tiempo_real` | Auto-refresh 2 min + alertas contextuales |
| Análisis Diario | `/analisis_diario` | Chart AGP interactivo + métricas clínicas |
| Tendencias | `/tendencias` | TIR/TAR/TBR histórico + CV% + tabla comparativa |
| Informe Médico | `/informe_medico` | Resumen de período + puntos para la consulta |

---

## API — endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Estado del servicio |
| GET | `/api/readings/latest` | Última lectura con contexto clínico |
| GET | `/api/readings/day/{date}` | Lecturas de un día |
| GET | `/api/readings/last-hours/{n}` | Últimas N horas |
| GET | `/api/summaries/day/{date}` | Métricas AGP del día |
| GET | `/api/summaries/weekly` | Resumen de los últimos 7 días |
| GET | `/api/summaries/chart/{date}` | PNG del perfil glucémico |
| GET | `/api/summaries/available-dates` | Fechas con datos disponibles |
| POST | `/api/readings` | Insertar nueva lectura (usado por monitor) |
| GET | `/api/reports/llm-status` | Estado de configuración Azure OpenAI |
| POST | `/api/reports/generate` | Generar informe médico con IA |
| GET | `/api/reports/daily-interpretation/{date}` | Interpretación diaria con cache |

Documentación interactiva: `http://localhost:8888/docs`

---

## Métricas clínicas implementadas

| Métrica | Descripción | Objetivo |
|---------|-------------|---------|
| **TIR** | Time In Range (70–180 mg/dL) | >70% |
| **TAR** | Time Above Range (>180 mg/dL) | <25% |
| **TBR** | Time Below Range (<70 mg/dL) | <4% |
| **TBR severo** | Tiempo <54 mg/dL | <1% |
| **CV%** | Variabilidad glucémica | <36% |
| **GMI** | Glucose Management Indicator (estima HbA1c) | <7% |
| **MAGE** | Amplitud media de excursiones glucémicas | <140 mg/dL |

Ver explicaciones en lenguaje simple: [GLOSARIO.md](GLOSARIO.md)

---

## Variables de entorno

Copiar `.env.example` → `.env` y completar:

| Variable | Descripción |
|----------|-------------|
| `LIBRE_EMAIL` / `LIBRE_PASSWORD` | Credenciales LibreLinkUp |
| `LIBRE_REGION` | Región API (`LA`, `EU`, `US`, `AP`) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alertas Telegram |
| `AZURE_OPENAI_API_KEY` / `ENDPOINT` / `DEPLOYMENT` | LLM (Fase 4) |
| `DATABASE_URL` | Ruta DuckDB (default: `data/glucose.duckdb`) |
| `API_PORT` | Puerto FastAPI (default: `8888`) |

---

## Datos de la paciente

Todo el historial clínico está en `Examenes_resultados/` y es **gitignoreado** por privacidad (PHI).
Incluye `patient_profile.json` — perfil clínico completo usado por el LLM (diagnósticos, medicamentos, laboratorios, alertas).
Ver instrucciones en [CLAUDE.md](CLAUDE.md) para agregar exámenes o fórmulas médicas localmente.
