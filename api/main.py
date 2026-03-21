"""
FastAPI backend — Glucose Intelligence Platform.
Punto de entrada de la API REST.

Ejecutar con:
    uvicorn api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import readings, summaries, reports, predictions
from api.services.db import initialize_schema


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Inicializa schema DuckDB al arrancar. La API es el unico proceso que toca DuckDB."""
    initialize_schema()
    yield


app = FastAPI(
    title="Glucose Intelligence API",
    description=(
        "Backend clínico para monitoreo glucémico con IA médica.\n\n"
        "Provee métricas AGP (Time In Range, CV, GMI) calculadas desde el CGM "
        "FreeStyle Libre de la paciente, charts diarios y resúmenes clínicos."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Permitir requests desde Streamlit en localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(readings.router,   prefix="/api/readings",   tags=["Lecturas"])
app.include_router(summaries.router,  prefix="/api/summaries",  tags=["Resúmenes AGP"])
app.include_router(reports.router,    prefix="/api/reports",    tags=["Informes médicos"])
app.include_router(predictions.router,prefix="/api/predictions",tags=["Predicciones"])


@app.get("/health", tags=["Sistema"])
def health_check() -> dict[str, str]:
    """Verifica que la API está corriendo y el DB es accesible."""
    from api.services.db import get_connection
    try:
        con = get_connection()
        count = con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        con.close()
        return {
            "status": "ok",
            "service": "glucose-intelligence-api",
            "readings_in_db": str(count),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/", tags=["Sistema"])
def root() -> dict[str, str]:
    return {
        "api": "Glucose Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
