# Glucose Intelligence Platform

> Sistema de monitoreo glucémico continuo con IA médica, alertas en tiempo real y dashboard clínico. Conectado a Abbott FreeStyle Libre via LibreLinkUp.

**Stack:** Python · FastAPI · Streamlit · Azure OpenAI GPT-4o · DuckDB · Telegram Bot
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
api/main.py (FastAPI)        ← Único escritor de glucose.duckdb (puerto 8888)
      │                          Endpoints: lecturas, métricas AGP, reportes LLM,
      │                          process-conversation-batch (para el bot)
      │
      ├──► llm/interpreter.py ← Azure OpenAI: interpretación, informes, resúmenes de chat
      │
      ├──► dashboard/app.py   ← Streamlit: 4 páginas de monitoreo clínico (puerto 8501)
      │
      └──► telegram_bot/bot.py ← Bot bidireccional: comandos + chat IA + memoria persistente
                │
                ▼
         data/conversations.duckdb ← Mensajes, resúmenes y notas clínicas de la paciente
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
| 5 | Telegram bot bidireccional + memoria persistente de conversaciones | ✅ Completo |
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

### Levantar el sistema completo

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

**Terminal 4 — Bot de Telegram:**
```bash
python -m telegram_bot.bot
```

El dashboard estará en: `http://localhost:8501`
La API estará en: `http://localhost:8888/docs`

---

## Bot de Telegram — comandos

| Comando | Descripción |
|---------|-------------|
| `/start` | Bienvenida e instrucciones |
| `/status` | Última lectura glucémica con contexto clínico |
| `/resumen` | Resumen AGP del día actual |
| `/semana` | Resumen semanal de métricas |
| `/ayuda` | Lista de comandos |
| `/limpiar` | Reinicia el contexto LLM (preserva historial en DB) |
| texto libre | Chat con la IA médica |

### Memoria persistente de conversaciones

El bot mantiene tres niveles de memoria en `data/conversations.duckdb`:

| Nivel | Qué guarda | Cuándo se usa |
|-------|-----------|---------------|
| **Mensajes recientes** | Todos los mensajes de los últimos 7 días (verbatim) | En cada respuesta LLM |
| **Resúmenes** | Resumen LLM de conversaciones >7 días (máx 300 palabras) | En cada respuesta LLM |
| **Notas de la paciente** | Hechos que Veronica mencionó que pueden contradecir el perfil clínico | Siempre, con máxima prioridad |

**Caso clave:** si la paciente dice "no compré la metformina", eso se captura como nota clínica y se incluye en todos los contextos futuros con precedencia sobre el perfil médico base.

La summarización ocurre automáticamente cada vez que una sesión expira (30 min de inactividad).

---

## Dashboard — páginas

| Página | Descripción |
|--------|-------------|
| Inicio | Glucosa actual + resumen del día + últimas 3h |
| Análisis Diario | Chart AGP interactivo + métricas clínicas por fecha |
| Tendencias | TIR/TAR/TBR histórico + CV% + tabla comparativa |
| Informe Médico | Informe de período con IA + puntos para la consulta |

---

## API — endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Estado del servicio |
| GET | `/api/readings/latest` | Última lectura con contexto clínico |
| GET | `/api/readings/day/{date}` | Lecturas de un día |
| GET | `/api/readings/last-hours/{n}` | Últimas N horas |
| POST | `/api/readings` | Insertar nueva lectura (monitor) |
| GET | `/api/summaries/day/{date}` | Métricas AGP del día |
| GET | `/api/summaries/weekly` | Resumen de los últimos 7 días |
| GET | `/api/summaries/chart/{date}` | PNG del perfil glucémico |
| GET | `/api/summaries/available-dates` | Fechas con datos disponibles |
| GET | `/api/reports/llm-status` | Estado de configuración Azure OpenAI |
| POST | `/api/reports/generate` | Generar informe médico con IA |
| GET | `/api/reports/daily-interpretation/{date}` | Interpretación diaria con cache |
| POST | `/api/reports/chat` | Chat interactivo con IA |
| POST | `/api/reports/process-conversation-batch` | Resumir mensajes + extraer notas clínicas |
| POST | `/api/admin/import-csv` | Importar CSVs de LibreView |
| GET | `/api/admin/db-status` | Estado de la base de datos |

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

---

## Variables de entorno

Copiar `.env.example` → `.env` y completar:

| Variable | Descripción |
|----------|-------------|
| `LIBRE_EMAIL` / `LIBRE_PASSWORD` | Credenciales LibreLinkUp |
| `LIBRE_REGION` | Región API (`LA`, `EU`, `US`, `AP`) |
| `TELEGRAM_BOT_TOKEN` | Token del bot (BotFather) |
| `TELEGRAM_CHAT_ID` | Chat ID autorizado (paciente) |
| `TELEGRAM_CAREGIVER_CHAT_ID` | Chat ID autorizado opcional (cuidador) |
| `TELEGRAM_CONVERSATION_TTL_MIN` | Minutos de inactividad antes de resumir (default: `30`) |
| `AZURE_OPENAI_API_KEY` / `ENDPOINT` / `DEPLOYMENT` | LLM (Fases 4+5) |
| `DATABASE_URL` | Ruta glucose.duckdb (default: `data/glucose.duckdb`) |
| `API_PORT` | Puerto FastAPI (default: `8888`) |
| `API_URL` | URL de la API para bot y dashboard (default: `http://localhost:8888`) |

---

## Datos de la paciente

Todo el historial clínico está en `Examenes_resultados/` y es **gitignoreado** por privacidad (PHI).
Incluye `patient_profile.json` — perfil clínico completo usado por el LLM (diagnósticos, medicamentos, laboratorios, alertas).

**Nota:** Las conversaciones del bot pueden actualizar el contexto clínico efectivo. Si la paciente menciona cambios en su tratamiento, estos se capturan como `patient_notes` en `conversations.duckdb` y tienen precedencia sobre `patient_profile.json` en futuras interacciones.

Ver instrucciones en [CLAUDE.md](CLAUDE.md) para agregar exámenes o fórmulas médicas localmente.
