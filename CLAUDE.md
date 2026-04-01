# CLAUDE.md — Glucose Intelligence Platform

## Contexto del proyecto

Sistema de monitoreo glucémico continuo con IA médica para el seguimiento de una paciente con **diabetes tipo 1**, conectado a Abbott FreeStyle Libre via LibreLinkUp. Incluye alertas por Telegram, dashboard Streamlit, API FastAPI y análisis clínico con Azure OpenAI.

**Repositorio:** `julianmora9494/glucose-monitor-llm` (privado)
**Stack:** Python · FastAPI · Streamlit · Azure OpenAI GPT-4o · DuckDB · Telegram

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
      ├──► api/main.py        ← FastAPI: endpoints AGP, lecturas, reportes
      │         │
      │         └──► llm/interpreter.py  ← Azure OpenAI (Fase 4)
      │
      └──► dashboard/app.py   ← Streamlit: 4 páginas de monitoreo clínico

scripts/import_history.py    ← Importación inicial: ~15 días del logbook LibreLinkUp
```

### Branches
- `main` → código estable en producción (monitor original)
- `feature/llm-platform` → desarrollo activo: FastAPI + Streamlit + Azure OpenAI

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
│   │   ├── reports.py         # /api/reports/* — informes médicos con Azure OpenAI
│   │   └── predictions.py     # /api/predictions/* — predicción glucémica (Fase 7)
│   └── services/
│       ├── db.py              # DuckDB: conexión, schema, CRUD
│       ├── metrics.py         # Cálculo TIR/TAR/TBR/CV/GMI/MAGE/episodios
│       ├── chart.py           # Generación PNG del perfil glucémico diario
│       └── llm_service.py     # Singleton GlucoseInterpreter + cache LLM
├── dashboard/                 # Streamlit (puerto 8501)
│   ├── app.py                 # Inicio + tiempo real: gauge, alertas, auto-refresh 2 min
│   ├── api_client.py          # Cliente HTTP centralizado para FastAPI
│   ├── components.py          # Componentes reutilizables: gauge, mini_chart, daily_chart...
│   └── pages/
│       ├── 1_analisis_diario.py  # Selector de fecha + chart AGP + tabla de lecturas
│       ├── 2_tendencias.py    # Barras apiladas TIR/TAR/TBR + CV% + tabla comparativa
│       └── 3_informe_medico.py   # Informe médico con IA (Azure OpenAI)
├── scripts/
│   └── import_history.py      # Importa ~15 días de logbook LibreLinkUp → DuckDB
├── llm/                       # Azure OpenAI
│   └── interpreter.py         # GlucoseInterpreter class (prompts inline)
├── Examenes_resultados/       # Datos clínicos PHI (SOLO LOCAL — gitignoreado)
│   └── patient_profile.json   # Perfil clínico completo para el LLM
├── data/                      # DuckDB (gitignoreado)
├── charts/                    # PNGs generados (gitignoreado)
├── .env                       # Credenciales reales (gitignoreado)
└── .env.example               # Template con placeholders (en git)
```

---

## Base de datos: DuckDB

Archivo: `data/glucose.duckdb`

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
Solo la API toca DuckDB. El monitor escribe via POST /api/readings.
Orden de arranque: FastAPI (DuckDB owner) → Monitor → Streamlit. Ver `start.ps1`.

### Bug conocido: ORDER BY LIMIT 1
DuckDB puede devolver filas stale con `ORDER BY timestamp DESC LIMIT 1`.
Usar `WHERE timestamp = (SELECT MAX(timestamp) FROM readings)` en su lugar.

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
| 5 | Telegram bot bidireccional + resúmenes nocturnos automáticos | ⏳ Pendiente |
| 6 | Informe médico PDF exportable | ⏳ Pendiente |
| 7 | Predicción glucémica 15–30 min | ⏳ Pendiente |

---

## Variables de entorno requeridas

Ver `.env.example`. Críticas:
- `LIBRE_EMAIL`, `LIBRE_PASSWORD`, `LIBRE_REGION`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` (Fase 4)
- `DATABASE_URL` (default: `data/glucose.duckdb`)
- `API_PORT` (default: `8888`)
- `API_URL` en dashboard (default: `http://localhost:8888`)
