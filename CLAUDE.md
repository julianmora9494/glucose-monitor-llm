# CLAUDE.md — Glucose Intelligence Platform

## Contexto del proyecto

Sistema de monitoreo glucémico continuo con IA médica para el seguimiento de una paciente con **diabetes tipo 1**, conectado a Abbott FreeStyle Libre via LibreLinkUp. Incluye alertas por Telegram, dashboard Streamlit, API FastAPI y análisis clínico con Azure OpenAI.

**Repositorio:** `julianmora9494/glucose-monitor-llm` (privado)
**Stack:** Python · FastAPI · Streamlit · Azure OpenAI GPT-4o · DuckDB · Telegram

---

## Reglas del proyecto

1. **Código en inglés, comentarios en español.**
2. **NUNCA commitear datos de la paciente.** Todo en `clinical_history/` está en `.gitignore`. La carpeta `clinical_history/processed/` contiene PHI (Protected Health Information) — solo existe localmente.
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
monitor/monitor_glucose.py   ← Polling cada 2 min, escribe en DuckDB, alertas Telegram
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
│   └── monitor_glucose.py     # Polling + alertas Telegram + escritura DuckDB
├── api/                       # FastAPI backend (Fase 2 — completo)
│   ├── main.py                # App + lifespan (initialize_schema on startup)
│   ├── routers/
│   │   ├── readings.py        # /api/readings/* — lecturas individuales
│   │   └── summaries.py       # /api/summaries/* — métricas AGP, charts, fechas
│   ├── models/                # Pydantic: ReadingResponse, DailySummary, WeeklySummary...
│   └── services/
│       ├── db.py              # DuckDB: conexión, schema, CRUD
│       ├── metrics.py         # Cálculo TIR/TAR/TBR/CV/GMI/MAGE/episodios
│       ├── chart.py           # Generación PNG del perfil glucémico diario
│       └── llm_service.py     # Azure OpenAI (stub — Fase 4)
├── dashboard/                 # Streamlit (Fase 3 — completo)
│   ├── app.py                 # Página principal: gauge + métricas hoy + mini-chart
│   ├── api_client.py          # Cliente HTTP centralizado para FastAPI (puerto 8080)
│   ├── components.py          # Componentes reutilizables: gauge, mini_chart, daily_chart...
│   └── pages/
│       ├── 1_tiempo_real.py   # Auto-refresh 2 min + alertas contextuales
│       ├── 2_analisis_diario.py  # Selector de fecha + chart AGP + tabla de lecturas
│       ├── 3_tendencias.py    # Barras apiladas TIR/TAR/TBR + CV% + tabla comparativa
│       └── 4_informe_medico.py   # Resumen de período + puntos para consulta médica
├── scripts/
│   └── import_history.py      # Importa ~15 días de logbook LibreLinkUp → DuckDB
├── llm/                       # Azure OpenAI (Fase 4 — pendiente)
│   ├── interpreter.py         # GlucoseInterpreter class
│   └── prompts/               # Prompts de sistema
├── clinical_history/          # Historial clínico (SOLO LOCAL — gitignoreado)
│   ├── uploads/               # PDFs, fotos de exámenes, export ChatGPT
│   └── processed/             # patient_profile.json, medical_notes.md
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
No se puede tener el monitor + la API + el script de importación escribiendo simultáneamente.
Orden seguro: detener monitor → importar historial → levantar API → levantar Streamlit → arrancar monitor.

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

## FastAPI — endpoints (puerto 8080)

| Ruta | Descripción |
|------|-------------|
| `GET /health` | Estado del servicio |
| `GET /api/readings/latest` | Última lectura + trend_description + alert_level + minutes_ago |
| `GET /api/readings/day/{date}` | Lecturas de un día |
| `GET /api/readings/last-hours/{n}` | Últimas N horas |
| `GET /api/summaries/day/{date}` | Métricas AGP del día + status dict |
| `GET /api/summaries/weekly` | Resumen 7 días (avg_tir, gmi, hypo/hyper totales...) |
| `GET /api/summaries/chart/{date}` | FileResponse PNG del perfil glucémico |
| `GET /api/summaries/available-dates` | Lista de fechas con datos |

---

## Dashboard Streamlit (puerto 8501)

Cada archivo de páginas tiene `sys.path.insert(0, ...)` para que Streamlit encuentre el paquete `dashboard` sin importar desde dónde se ejecute.

El `api_client.py` lee `API_URL` del env (default `http://localhost:8080`). Para cambiar el puerto basta con setear `API_URL=http://localhost:XXXX` en el `.env`.

### Fondos de charts
Todos los charts usan `plot_bgcolor="rgba(0,0,0,0)"` y `paper_bgcolor="rgba(0,0,0,0)"` para adaptarse al dark/light mode de Streamlit sin fondo blanco.

---

## Scripts útiles

```bash
# Importar historial completo del sensor (~15 días del logbook LibreLinkUp)
# Ejecutar UNA SOLA VEZ antes de levantar la API (DuckDB single-writer)
python scripts/import_history.py

# Levantar FastAPI
uvicorn api.main:app --port 8080 --reload

# Levantar dashboard
streamlit run dashboard/app.py

# Monitor de polling continuo
python monitor/monitor_glucose.py
```

---

## Contexto clínico de la paciente

> Los datos específicos están en `clinical_history/processed/patient_profile.json` (solo local).

**Perfil general (no PHI):**
- DM1 + hipotiroidismo
- Esquema: insulina basal (degludec) + rápida titulable + metformina 850 mg
- Monitoreo: FreeStyle Libre 2 Plus
- HbA1c objetivo: <7% (actual por encima del objetivo)
- Alertas: hipoglucemia <70, hiperglucemia >180, caídas/subidas rápidas >2 mg/dL/min

**El LLM (Fase 4) cargará el perfil completo** desde `patient_profile.json` en cada llamada.

---

## Cómo agregar información de la paciente (localmente)

### Nuevos exámenes
1. Copiar PDF/foto a `clinical_history/uploads/examenes/`
2. Pegar el texto aquí → yo actualizo `patient_profile.json`

### Nueva fórmula médica
1. Copiar a `clinical_history/uploads/formulas/`
2. Actualizar `current_medications` en `patient_profile.json`

### Datos pendientes
- Nombre exacto de la insulina rápida (¿glulisina / aspart?)
- Dosis de levotiroxina
- Resultados pendientes: prolactina, VIH, hepatitis B, Treponema, albúmina/creatinina

---

## Fases de desarrollo

| Fase | Módulo | Estado |
|------|--------|--------|
| 0 | Monitor CGM + alertas Telegram | ✅ Producción (`main`) |
| 1 | DuckDB + métricas AGP + chart diario único | ✅ Completo |
| 2 | FastAPI endpoints funcionales | ✅ Completo |
| 3 | Streamlit dashboard — 4 páginas clínicas | ✅ Completo |
| 4 | Azure OpenAI: interpretación médica en dashboard e informe | ⏳ Siguiente |
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
- `API_PORT` (default: `8080`)
- `API_URL` en dashboard (default: `http://localhost:8080`)
