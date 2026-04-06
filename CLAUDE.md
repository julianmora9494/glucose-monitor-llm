# CLAUDE.md — Glucose Intelligence Platform

## Contexto del proyecto

Sistema de monitoreo glucémico continuo con IA médica para el seguimiento de una paciente con **diabetes tipo 1**, conectado a Abbott FreeStyle Libre via LibreLinkUp. Incluye alertas por Telegram, bot bidireccional con memoria persistente, dashboard Streamlit, API FastAPI y análisis clínico con Azure OpenAI.

**Repositorio:** `julianmora9494/glucose-monitor-llm` (privado)
**Stack:** Python · FastAPI · Streamlit · Azure OpenAI GPT-4o · DuckDB · Telegram Bot

---

## Reglas del proyecto

1. **Código en inglés, comentarios en español.**
2. **NUNCA commitear datos de la paciente.** `Examenes_resultados/` está en `.gitignore` y contiene PHI (Protected Health Information) — solo existe localmente.
3. **NUNCA commitear `.env`** con valores reales. Solo `.env.example` con placeholders.
4. `requirements.txt` con versiones fijas.
5. Type hints en todo el código Python.
6. Antes de implementar, proponer arquitectura si el cambio es significativo.

---

## Arquitectura

```
LibreLinkUp API (FreeStyle Libre CGM)
      │
      ▼
monitor/monitor_glucose.py   ← Polling cada 2 min, escribe via POST /api/readings, alertas Telegram
      │
      ▼
data/glucose.duckdb          ← Base de datos central (LOCAL, gitignoreado)
      │
      ├──► api/main.py        ← FastAPI: endpoints AGP, lecturas, reportes, process-conversation-batch
      │         │
      │         └──► llm/interpreter.py  ← Azure OpenAI (Fase 4+5)
      │
      ├──► dashboard/app.py   ← Streamlit: 4 páginas de monitoreo clínico
      │
      └──► telegram_bot/bot.py ← Bot bidireccional: comandos + chat IA + memoria persistente
                │
                ▼
         data/conversations.duckdb ← Historial, resúmenes y notas de la paciente (bot-owned)

scripts/import_history.py    ← Importación inicial: ~15 días del logbook LibreLinkUp
```

### Branches
- `main` → código estable en producción (monitor original)
- `feature/llm-platform` → desarrollo activo: FastAPI + Streamlit + Azure OpenAI + Telegram bot

---

## Estructura de archivos

```
glucose-monitor-llm/
├── monitor/                   # Servicio CGM (producción)
│   └── monitor_glucose.py     # Polling + alertas Telegram + POST /api/readings
├── api/                       # FastAPI backend (puerto 8888)
│   ├── main.py                # App + lifespan (initialize_schema on startup)
│   ├── routers/
│   │   ├── readings.py        # /api/readings/* — lecturas + POST desde monitor
│   │   ├── summaries.py       # /api/summaries/* — métricas AGP, charts, fechas
│   │   ├── reports.py         # /api/reports/* — informes médicos + process-conversation-batch
│   │   ├── admin.py           # /api/admin/* — import CSV LibreView, db-status
│   │   └── predictions.py     # /api/predictions/* — predicción glucémica (Fase 7)
│   └── services/
│       ├── db.py              # DuckDB: conexión, schema, CRUD (glucose.duckdb)
│       ├── metrics.py         # Cálculo TIR/TAR/TBR/CV/GMI/MAGE/episodios
│       ├── chart.py           # Generación PNG del perfil glucémico diario
│       └── llm_service.py     # Singleton GlucoseInterpreter + cache LLM + process_conversation_batch
├── dashboard/                 # Streamlit (puerto 8501)
│   ├── app.py                 # Inicio + tiempo real: gauge, alertas, auto-refresh 2 min
│   ├── api_client.py          # Cliente HTTP centralizado para FastAPI
│   ├── components.py          # Componentes reutilizables: gauge, mini_chart, daily_chart...
│   └── pages/
│       ├── 1_analisis_diario.py  # Selector de fecha + chart AGP + tabla de lecturas
│       ├── 2_tendencias.py    # Barras apiladas TIR/TAR/TBR + CV% + tabla comparativa
│       └── 3_informe_medico.py   # Informe médico con IA (Azure OpenAI)
├── telegram_bot/              # Bot bidireccional (Fase 5)
│   ├── bot.py                 # Punto de entrada: polling + registro de handlers
│   ├── handlers.py            # Comandos + chat IA + persistencia + cleanup con summarización
│   ├── memory.py              # ConversationStore: persistencia en conversations.duckdb
│   ├── conversation.py        # ConversationManager: TTL de sesiones (sin historial en RAM)
│   ├── api_client.py          # Cliente HTTP async para FastAPI (incluye process_conversation_batch)
│   ├── security.py            # Autorización por TELEGRAM_CHAT_ID / TELEGRAM_CAREGIVER_CHAT_ID
│   ├── formatters.py          # Formateadores de mensajes Telegram
│   └── __init__.py
├── scripts/
│   └── import_history.py      # Importa ~15 días de logbook LibreLinkUp → DuckDB
├── llm/                       # Azure OpenAI
│   └── interpreter.py         # GlucoseInterpreter: interpret, report, chat, summarize, extract_notes
├── Examenes_resultados/       # Datos clínicos PHI (SOLO LOCAL — gitignoreado)
│   └── patient_profile.json   # Perfil clínico completo para el LLM
├── data/                      # DuckDB files (gitignoreado)
│   ├── glucose.duckdb         # Lecturas CGM + resúmenes diarios (propiedad de la API)
│   └── conversations.duckdb   # Historial del bot (propiedad del bot de Telegram)
├── charts/                    # PNGs generados (gitignoreado)
├── .env                       # Credenciales reales (gitignoreado)
└── .env.example               # Template con placeholders (en git)
```

---

## Base de datos: glucose.duckdb

Archivo: `data/glucose.duckdb` — propiedad exclusiva de la API FastAPI.

### Schema

```sql
CREATE TABLE readings (
    id              INTEGER PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    glucose_mgdl    DOUBLE NOT NULL,
    trend           VARCHAR,
    delta_mgdl      DOUBLE,
    dt_min          DOUBLE,
    slope_mgdl_min  DOUBLE,
    percent_change  DOUBLE,
    range_type      VARCHAR   -- 'very_low','low','normal','high','very_high'
);

CREATE TABLE daily_summaries (
    date                DATE PRIMARY KEY,
    reading_count       INTEGER,
    avg_glucose         DOUBLE,
    std_glucose         DOUBLE,
    cv_percent          DOUBLE,
    tir_percent         DOUBLE,
    tar_percent         DOUBLE,
    tbr_percent         DOUBLE,
    tbr_severe_percent  DOUBLE,
    gmi_percent         DOUBLE,
    mage_mgdl           DOUBLE,
    hypo_episodes       INTEGER,
    hyper_episodes      INTEGER,
    min_glucose         DOUBLE,
    max_glucose         DOUBLE,
    llm_summary         TEXT      -- Interpretación LLM (cache — no re-generar)
);
```

**Nota:** No hay columna `created_at` en `readings` — el monitor no la escribe. No agregarla.

### Deduplicación
Toda inserción verifica `timestamp` exacto antes de insertar. Safe para re-ejecutar.

### DuckDB es single-writer
Solo la API toca `glucose.duckdb`. El monitor escribe via POST /api/readings.
Orden de arranque: FastAPI (DuckDB owner) → Monitor → Streamlit. Ver `start.ps1`.

### Bug conocido: ORDER BY LIMIT 1
DuckDB puede devolver filas stale con `ORDER BY timestamp DESC LIMIT 1`.
Usar `WHERE timestamp = (SELECT MAX(timestamp) FROM readings)` en su lugar.

---

## Base de datos: conversations.duckdb

Archivo: `data/conversations.duckdb` — propiedad exclusiva del bot de Telegram.
Separado de `glucose.duckdb` para no violar el single-writer constraint de la API.

### Schema

```sql
CREATE TABLE conversation_messages (
    id          INTEGER PRIMARY KEY,
    chat_id     BIGINT NOT NULL,
    role        VARCHAR NOT NULL,   -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL
);

CREATE TABLE conversation_summaries (
    id              INTEGER PRIMARY KEY,
    chat_id         BIGINT NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    summary         TEXT NOT NULL,        -- resumen LLM de mensajes >7 días
    message_count   INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE patient_notes (
    id          INTEGER PRIMARY KEY,
    chat_id     BIGINT NOT NULL,
    content     TEXT NOT NULL,    -- "Veronica no está tomando metformina desde 2026-03-28"
    note_type   VARCHAR,          -- 'medication' | 'correction' | 'symptom' | 'behavior'
    source_date DATE,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL
);
```

### Flujo de memoria del bot

El contexto enviado al LLM en cada mensaje se construye con esta prioridad:

```
1. patient_profile.json         (siempre — perfil base)
2. patient_notes activas         (siempre — TIENEN PRECEDENCIA sobre el perfil si contradicen)
3. conversation_summaries        (períodos >7 días, compacto)
4. conversation_messages recientes (últimos 7 días / máx 40 mensajes, verbatim)
5. pregunta actual
```

### Summarización automática
- **Trigger:** `cleanup_job` cada 10 min detecta sesiones expiradas (TTL 30 min)
- **Proceso:** mensajes >7 días sin cobertura de resumen → POST `/api/reports/process-conversation-batch` → LLM genera `{summary, notes}` → se persiste en conversations.duckdb
- **Mínimo:** 4 mensajes (2 turnos) para justificar un resumen

### Patient notes — caso crítico
Si Veronica dice "no compré la metformina" en el chat → al expirar la sesión, `extract_patient_notes()` captura ese hecho → se guarda como nota activa → en futuras conversaciones aparece antes del historial con el aviso explícito de que tiene precedencia sobre el perfil clínico base.

### /limpiar
No borra el historial de DB. Solo setea `context_since = now()` en la sesión en memoria, por lo que el LLM no recibe mensajes anteriores al clear. Los mensajes se siguen preservando para resumir.

---

## Métricas AGP implementadas

| Métrica | Fórmula | Target |
|---------|---------|--------|
| **TIR** | % lecturas en 70–180 mg/dL | >70% |
| **TAR** | % lecturas >180 mg/dL | <25% |
| **TBR** | % lecturas <70 mg/dL | <4% |
| **TBR severo** | % lecturas <54 mg/dL | <1% |
| **CV%** | (std / mean) × 100 | <36% |
| **GMI** | 3.31 + 0.02392 × mean_glucose | <7% |
| **MAGE** | Promedio excursiones glucémicas >1 SD | <140 mg/dL |

---

## FastAPI — endpoints (puerto 8888)

| Ruta | Descripción |
|------|-------------|
| `GET /health` | Estado del servicio |
| `POST /api/readings` | Recibe lectura del monitor (deduplicación por timestamp) |
| `GET /api/readings/latest` | Última lectura + trend_description + alert_level + minutes_ago |
| `GET /api/readings/day/{date}` | Lecturas de un día |
| `GET /api/readings/last-hours/{n}` | Últimas N horas |
| `GET /api/summaries/day/{date}` | Métricas AGP del día + status dict |
| `GET /api/summaries/weekly` | Resumen 7 días (avg_tir, gmi, hypo/hyper totales...) |
| `GET /api/summaries/chart/{date}` | FileResponse PNG del perfil glucémico |
| `GET /api/summaries/available-dates` | Lista de fechas con datos |
| `GET /api/reports/llm-status` | Verifica si Azure OpenAI está configurado |
| `POST /api/reports/generate` | Genera informe médico con IA (período) |
| `GET /api/reports/daily-interpretation/{date}` | Interpretación diaria con IA (cache) |
| `POST /api/reports/chat` | Chat interactivo con IA (perfil + historial CGM) |
| `POST /api/reports/process-conversation-batch` | Resume mensajes + extrae notas clínicas (usado por el bot) |
| `POST /api/admin/import-csv` | Importa CSVs de LibreView a DuckDB |
| `GET /api/admin/db-status` | Estado de la base de datos |

---

## Telegram Bot — comandos

| Comando | Descripción |
|---------|-------------|
| `/start` | Bienvenida e instrucciones |
| `/status` | Última lectura glucémica con contexto clínico |
| `/resumen` | Resumen AGP del día actual |
| `/semana` | Resumen semanal de métricas |
| `/ayuda` / `/help` | Lista de comandos |
| `/limpiar` | Reinicia el contexto LLM (preserva historial en DB) |
| texto libre | Chat con IA médica con contexto persistente completo |

**Autorización:** solo los `chat_id` en `TELEGRAM_CHAT_ID` y `TELEGRAM_CAREGIVER_CHAT_ID` pueden usar el bot.

**Bug corregido:** `load_dotenv()` debe llamarse ANTES de importar `telegram_bot.security`, ya que `_load_allowed_chat_ids()` corre al importar el módulo.

---

## Dashboard Streamlit (puerto 8501)

Cada archivo de páginas tiene `sys.path.insert(0, ...)` para que Streamlit encuentre el paquete `dashboard` sin importar desde dónde se ejecute.

El `api_client.py` lee `API_URL` del env (default `http://localhost:8888`).

### Fondos de charts
Todos los charts usan `plot_bgcolor="rgba(0,0,0,0)"` y `paper_bgcolor="rgba(0,0,0,0)"` para adaptarse al dark/light mode de Streamlit sin fondo blanco.

---

## Scripts útiles

```bash
# Importar historial completo del sensor (~15 días del logbook LibreLinkUp)
# Ejecutar UNA SOLA VEZ antes de levantar la API (DuckDB single-writer)
python scripts/import_history.py

# Levantar FastAPI
uvicorn api.main:app --port 8888 --reload

# Levantar dashboard
streamlit run dashboard/app.py

# Monitor de polling continuo
python monitor/monitor_glucose.py

# Bot de Telegram bidireccional
python -m telegram_bot.bot
```

---

## Contexto clínico de la paciente

> Perfil completo en `Examenes_resultados/patient_profile.json` (solo local, gitignoreado).

**Perfil general (no PHI):**
- DM1 + hipotiroidismo
- Esquema: insulina basal degludec 40 UI/día + rápida glulisina (20/20/18 UI titulable) + metformina 850 mg
- Monitoreo: FreeStyle Libre 2 Plus
- HbA1c: 7.82% (objetivo <7%)
- Alertas: hipoglucemia <70, hiperglucemia >180, caídas/subidas rápidas >2 mg/dL/min

**El LLM carga el perfil completo** desde `patient_profile.json` en cada llamada via `llm/interpreter.py`.

**IMPORTANTE:** Lo que la paciente diga en el chat puede contradecir el perfil. Las `patient_notes` en `conversations.duckdb` tienen precedencia. Siempre verificar si hay notas activas antes de asumir que el perfil está vigente.

---

## Cómo agregar información de la paciente

1. Copiar PDF/foto a `Examenes_resultados/`
2. Actualizar `Examenes_resultados/patient_profile.json` con los nuevos datos
3. Reiniciar uvicorn para que el interpreter recargue el perfil

---

## Fases de desarrollo

| Fase | Módulo | Estado |
|------|--------|--------|
| 0 | Monitor CGM + alertas Telegram | ✅ Producción (`main`) |
| 1 | DuckDB + métricas AGP + chart diario único | ✅ Completo |
| 2 | FastAPI endpoints funcionales | ✅ Completo |
| 3 | Streamlit dashboard — 4 páginas clínicas | ✅ Completo |
| 4 | Azure OpenAI: interpretación médica en dashboard e informe | ✅ Completo |
| 5 | Telegram bot bidireccional + memoria persistente de conversaciones | ✅ Completo |
| 6 | Informe médico PDF exportable | ⏳ Pendiente |
| 7 | Predicción glucémica 15–30 min | ⏳ Pendiente |

---

## Variables de entorno requeridas

Ver `.env.example`. Críticas:
- `LIBRE_EMAIL`, `LIBRE_PASSWORD`, `LIBRE_REGION`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `TELEGRAM_CAREGIVER_CHAT_ID` (opcional — segundo usuario autorizado)
- `TELEGRAM_CONVERSATION_TTL_MIN` (default: `30` — minutos de inactividad antes de resumir)
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` (Fase 4+5)
- `DATABASE_URL` (default: `data/glucose.duckdb`)
- `API_PORT` (default: `8888`)
- `API_URL` en dashboard y bot (default: `http://localhost:8888`)
