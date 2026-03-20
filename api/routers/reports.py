"""
Router: generación de informes médicos con Azure OpenAI.
"""

from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class MedicalReportRequest(BaseModel):
    date_from: date
    date_to: date
    include_recommendations: bool = True
    language: str = "es"             # Idioma del informe


class MedicalReportResponse(BaseModel):
    period: str
    executive_summary: str           # Resumen ejecutivo en lenguaje médico accesible
    glycemic_control: str            # Análisis del control glucémico
    patterns_detected: list[str]     # Patrones clínicos identificados
    recommendations: list[str]       # Recomendaciones personalizadas
    for_physician: str               # Sección técnica para el médico tratante
    generated_at: str


@router.post("/generate", response_model=MedicalReportResponse)
def generate_medical_report(request: MedicalReportRequest) -> MedicalReportResponse:
    """
    Genera un informe médico completo usando Azure OpenAI.
    Combina métricas AGP con historial clínico de la paciente.
    """
    # TODO: implementar con llm/interpreter.py + patient_profile.json
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/pdf/{report_date}")
def generate_pdf_report(report_date: date) -> dict[str, str]:
    """
    Genera un PDF del informe médico para llevar a la consulta.
    Formato estándar AGP compatible con lo que usan los endocrinólogos.
    """
    # TODO: implementar con reportlab
    raise HTTPException(status_code=501, detail="Not implemented yet")
