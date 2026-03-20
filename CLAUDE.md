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
      ├──► api/main.py       ← FastAPI: endpoints AGP, lecturas, reportes, predicciones
      │         │
      │         └──► llm/interpreter.py  ← Azure OpenAI: interpretación médica
      │
      └──► dashboard/app.py  ← Streamlit: 4 páginas de monitoreo clínico
```

### Branches
- `main` → código estable en producción (monitor actual funcionando)
- `feature/llm-platform` → desarrollo activo: FastAPI + Streamlit + Azure OpenAI

---

## Estructura de archivos

```
glucose-monitor-llm/
├── monitor/                  # Servicio CGM (producción)
│   └── monitor_glucose.py    # Polling + alertas Telegram + escritura DuckDB
├── api/                      # FastAPI backend
│   ├── main.py
│   ├── routers/              # readings, summaries, reports, predictions
│   ├── models/               # Pydantic models
│   └── services/             # db.py (DuckDB), metrics.py (AGP), llm_service.py
├── dashboard/                # Streamlit
│   ├── app.py
│   └── pages/                # 1_tiempo_real, 2_analisis_diario, 3_tendencias, 4_informe_medico
├── llm/                      # Azure OpenAI
│   ├── interpreter.py        # GlucoseInterpreter class
│   └── prompts/              # Prompts de sistema
├── clinical_history/         # Historial clínico (TODO gitignoreado — solo local)
│   ├── uploads/              # Archivos raw: PDFs, fotos de exámenes, export ChatGPT
│   └── processed/            # patient_profile.json, medical_notes.md (generados localmente)
├── data/                     # DuckDB database (gitignoreado)
├── charts/                   # Charts generados (gitignoreado)
├── .env                      # Credenciales reales (gitignoreado)
└── .env.example              # Template con placeholders (en git)
```

---

## Base de datos: DuckDB

Archivo: `data/glucose.duckdb`

### Schema

```sql
-- Lecturas del CGM
CREATE TABLE readings (
    id          INTEGER PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    glucose_mgdl DOUBLE NOT NULL,
    trend       VARCHAR,
    delta_mgdl  DOUBLE,
    dt_min      DOUBLE,
    slope_mgdl_min DOUBLE,
    percent_change DOUBLE,
    range_type  VARCHAR,  -- 'very_low', 'low', 'normal', 'high', 'very_high'
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Resúmenes diarios (calculados, no redundar desde readings)
CREATE TABLE daily_summaries (
    date        DATE PRIMARY KEY,
    reading_count INTEGER,
    avg_glucose DOUBLE,
    std_glucose DOUBLE,
    cv_percent  DOUBLE,
    tir_percent DOUBLE,   -- Time In Range 70-180
    tar_percent DOUBLE,   -- Time Above Range >180
    tbr_percent DOUBLE,   -- Time Below Range <70
    tbr_severe_percent DOUBLE,  -- <54 mg/dL
    gmi_percent DOUBLE,   -- Glucose Management Indicator (estima HbA1c)
    mage_mgdl   DOUBLE,   -- Mean Amplitude of Glycemic Excursions
    hypo_episodes INTEGER,
    hyper_episodes INTEGER,
    min_glucose DOUBLE,
    max_glucose DOUBLE,
    llm_summary TEXT      -- Interpretación diaria del LLM (guardada para no re-generar)
);
```

---

## Métricas AGP implementadas

| Métrica | Fórmula | Target paciente |
|---------|---------|----------------|
| **TIR** | % lecturas en 70-180 mg/dL | >70% |
| **TAR** | % lecturas >180 mg/dL | <25% |
| **TBR** | % lecturas <70 mg/dL | <4% |
| **TBR severo** | % lecturas <54 mg/dL | <1% |
| **CV%** | (std/mean) × 100 | <36% |
| **GMI** | 3.31 + 0.02392 × mean_glucose | Objetivo del médico |
| **eA1C** | (GMI - 3.31) / 0.02392 → se reporta como GMI | <7% |
| **MAGE** | Promedio de excursiones glucémicas >1 SD | <140 mg/dL |

---

## Contexto clínico de la paciente

> Los datos específicos están en `clinical_history/processed/patient_profile.json` (solo local).

**Perfil general (no PHI):**
- DM1 + hipotiroidismo
- Esquema: insulina basal + rápida titulable + metformina
- Monitoreo: FreeStyle Libre 2 Plus
- HbA1c objetivo: <7% (actual por encima del objetivo)
- Alertas configuradas: hipoglucemia <70, hiperglucemia >180, caídas/subidas rápidas

**El LLM carga el perfil completo** desde `clinical_history/processed/patient_profile.json`
en cada llamada a Azure OpenAI para personalizar las interpretaciones.

---

## Cómo agregar información de la paciente (localmente)

### Nuevos exámenes o resultados
1. Copiar PDF o foto a `clinical_history/uploads/examenes/`
2. Editar manualmente `clinical_history/processed/patient_profile.json`
3. O pegar el texto aquí y yo proceso y actualizo el JSON

### Nueva fórmula médica
1. Copiar a `clinical_history/uploads/formulas/`
2. Actualizar `current_medications` en `patient_profile.json`

### Datos pendientes de completar
- Nombre exacto de la insulina rápida (¿glulisina?)
- Dosis de levotiroxina
- Resultados: prolactina, VIH, hepatitis B, Treponema
- Relación albúmina/creatinina en orina
- Registro de glucosas 3-7 días del Libre

---

## Fases de desarrollo

| Fase | Módulo | Estado |
|------|--------|--------|
| 0 | Monitor actual funcionando | ✅ Producción (branch main) |
| 1 | DuckDB + métricas AGP + chart diario único | 🚧 En desarrollo |
| 2 | FastAPI endpoints funcionales | ⏳ Pendiente |
| 3 | Streamlit dashboard con datos reales | ⏳ Pendiente |
| 4 | Azure OpenAI: interpretación en alertas y resumen nocturno | ⏳ Pendiente |
| 5 | Telegram mejorado: bot bidireccional + resúmenes diarios | ⏳ Pendiente |
| 6 | Informe médico PDF + AGP semanal | ⏳ Pendiente |
| 7 | Predicción glucémica 15-30 min | ⏳ Pendiente |

---

## Variables de entorno requeridas

Ver `.env.example` para la lista completa. Las críticas:
- `LIBRE_EMAIL`, `LIBRE_PASSWORD`, `LIBRE_REGION` — LibreLinkUp
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Alertas
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` — LLM
- `DATABASE_URL` — ruta al archivo DuckDB (default: `data/glucose.duckdb`)
