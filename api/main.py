"""
FastAPI backend — Glucose Intelligence Platform.
Punto de entrada de la API REST.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import readings, summaries, reports, predictions


app = FastAPI(
    title="Glucose Intelligence API",
    description="Backend clínico para monitoreo glucémico con IA médica",
    version="0.1.0",
)

# Permitir requests desde Streamlit en localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(readings.router, prefix="/api/readings", tags=["Lecturas"])
app.include_router(summaries.router, prefix="/api/summaries", tags=["Resúmenes clínicos"])
app.include_router(reports.router, prefix="/api/reports", tags=["Informes médicos"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Predicciones"])


@app.get("/health")
def health_check() -> dict[str, str]:
    """Endpoint de salud para verificar que la API está corriendo."""
    return {"status": "ok", "service": "glucose-intelligence-api"}
