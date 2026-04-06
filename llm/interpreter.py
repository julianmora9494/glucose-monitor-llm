"""
Intérprete médico — Azure OpenAI.
Genera análisis clínicos personalizados basados en los datos glucémicos
y el historial clínico de la paciente.
"""

import json
import logging
from pathlib import Path
from typing import Any

from openai import AzureOpenAI

logger = logging.getLogger(__name__)


PATIENT_PROFILE_PATH = Path("Examenes_resultados/patient_profile.json")

SYSTEM_PROMPT_TEMPLATE = """
Eres un médico endocrinólogo especialista en diabetes con 20 años de experiencia.
Tienes acceso al perfil clínico de la paciente y a sus datos glucémicos del CGM (FreeStyle Libre).

PERFIL DE LA PACIENTE:
{patient_profile}

DIRECTRICES CLÍNICAS:
- Usa el estándar AGP (Ambulatory Glucose Profile) para interpretar datos de CGM
- Las métricas objetivo para esta paciente son TIR >70%, TAR <25%, TBR <4%, CV <36%
- Detecta patrones clínicos: fenómeno del amanecer, hipoglucemia nocturna, picos post-prandiales
- Habla en español, con lenguaje claro para el paciente y su cuidador
- Sé empático pero preciso. Cuando algo requiere atención médica urgente, indícalo claramente
- Nunca reemplazas la consulta médica; siempre recomienda hablar con el médico tratante
"""


def load_patient_profile() -> dict[str, Any]:
    """Carga el perfil clínico de la paciente desde el archivo JSON."""
    if not PATIENT_PROFILE_PATH.exists():
        return {"note": "Perfil clínico no disponible. Ver clinical_history/README.md"}

    with open(PATIENT_PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_system_prompt() -> str:
    """Construye el prompt de sistema con el perfil de la paciente."""
    profile = load_patient_profile()
    return SYSTEM_PROMPT_TEMPLATE.format(
        patient_profile=json.dumps(profile, ensure_ascii=False, indent=2)
    )


class GlucoseInterpreter:
    """Intérprete médico basado en Azure OpenAI."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-02-01",
    ) -> None:
        self.client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self.deployment = deployment
        self.system_prompt = get_system_prompt()

    def interpret_daily_summary(self, summary_data: dict[str, Any]) -> str:
        """
        Genera interpretación clínica del resumen diario.
        Se usa para el mensaje de Telegram de la noche y el dashboard.
        """
        user_message = f"""
        Analiza el siguiente resumen glucémico del día de la paciente:

        {json.dumps(summary_data, ensure_ascii=False, indent=2)}

        Proporciona:
        1. Un párrafo de resumen ejecutivo (2-3 oraciones)
        2. Lo más relevante del día (positivo y negativo)
        3. Una recomendación concreta para mañana
        4. Nivel de control: BUENO / REGULAR / REQUIERE ATENCIÓN

        Sé conciso. Máximo 150 palabras.
        """

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=400,

        )

        return response.choices[0].message.content or ""

    def interpret_alert(self, alert_data: dict[str, Any]) -> str:
        """
        Enriquece una alerta con contexto clínico.
        Ejemplo: 'Glucosa alta a las 13:45 → posible pico post-prandial del almuerzo'.
        """
        user_message = f"""
        Se acaba de disparar la siguiente alerta glucémica:

        {json.dumps(alert_data, ensure_ascii=False, indent=2)}

        En 1-2 oraciones, explica:
        - Qué está pasando clínicamente
        - Posible causa basada en el horario y el historial de la paciente
        - Qué hacer ahora

        Sé muy conciso. Este mensaje va en Telegram.
        """

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=150,

        )

        return response.choices[0].message.content or ""

    def generate_medical_report(
        self,
        period_data: dict[str, Any],
        include_recommendations: bool = True,
    ) -> dict[str, str]:
        """
        Genera informe médico completo para llevar a la consulta.
        Retorna diccionario con secciones separadas del informe.
        """
        user_message = f"""
        Genera un informe médico DETALLADO y EXPLICATIVO para el siguiente período.
        Este informe es para que la paciente y su cuidador lo lleven a la consulta con el endocrinólogo.

        DATOS DEL PERÍODO:
        {json.dumps(period_data, ensure_ascii=False, indent=2)}

        INSTRUCCIONES IMPORTANTES:
        - NO repitas las métricas numéricas (TIR%, TAR%, CV%, etc.) como lista — el dashboard ya las muestra.
        - En su lugar, INTERPRETA qué significan clínicamente para ESTA paciente específica.
        - Relaciona los datos con su perfil: medicamentos actuales, HbA1c, comorbilidades.
        - Explica en lenguaje claro pero completo, como si hablaras con la paciente y su familia.
        - Identifica patrones temporales: ¿los picos son post-prandiales? ¿hay fenómeno del amanecer?
        - Conecta los hallazgos con posibles causas (alimentación, insulina, estrés, horarios).

        El informe debe incluir estas secciones en formato JSON:
        {{
            "executive_summary": "Resumen narrativo del período (4-5 oraciones). Explica cómo le fue a la paciente, qué mejoró, qué empeoró y por qué es relevante clínicamente. Relaciona con su HbA1c y esquema de insulina.",
            "glycemic_control": "Análisis clínico detallado: interpreta los datos en el contexto de su DM1, esquema basal-bolo, metformina. Explica qué indican los patrones glucémicos sobre la efectividad del tratamiento actual. Mínimo 150 palabras.",
            "patterns_detected": ["Cada patrón debe incluir: descripción + hora/momento + posible causa + implicación clínica"],
            "recommendations": ["Cada recomendación debe ser específica y accionable. Incluir: qué hacer, cuándo, y por qué. Ejemplo: 'Revisar con el médico la dosis de glulisina del almuerzo (actualmente 20 UI) — los picos post-prandiales de 12-14h sugieren que podría necesitar ajuste'"],
            "for_physician": "Sección técnica con lenguaje médico formal: resumen de métricas AGP, patrones identificados, posibles ajustes terapéuticos sugeridos para discutir. Incluir: evaluación de la dosis basal (degludec 40 UI), ratio insulina/CHO, posible interacción con metformina 850mg."
        }}

        {'Incluye recomendaciones específicas, accionables y personalizadas para esta paciente.' if include_recommendations else 'No incluyas recomendaciones.'}
        Mínimo 500 palabras en total. Este informe debe aportar valor clínico real, no solo repetir números.
        """

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=3000,

            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def answer_question(
        self,
        question: str,
        glucose_context: dict[str, Any],
        conversation_history: list[dict[str, str]],
        channel: str = "dashboard",
    ) -> str:
        """
        Responde preguntas del usuario sobre la paciente, integrando
        el perfil clinico completo + historial glucemico del CGM.

        Args:
            channel: 'telegram' ajusta el estilo para chat directo con la paciente
                     (más conciso, preguntas proactivas sobre comida/insulina).
                     'dashboard' usa el estilo completo por defecto.
        """
        context_message = f"""
DATOS GLUCEMICOS HISTORICOS DEL CGM:
{json.dumps(glucose_context, ensure_ascii=False, indent=2)}

Usa toda esta informacion junto con el perfil clinico de la paciente
para responder la pregunta del usuario. Se preciso, empático y clinicamente riguroso.
Responde en español. Si la pregunta requiere informacion que no tienes, indicalo claramente.
"""

        # Instrucciones adicionales para el canal de Telegram
        if channel == "telegram":
            context_message += """
CANAL: Telegram (chat directo con la paciente o su cuidador)
INSTRUCCIONES PARA ESTE CANAL:
- Sé conciso: máximo 300 palabras por respuesta
- Haz preguntas proactivas y relevantes al final de tu respuesta según el contexto clínico:
  * Si la glucosa está alta (>180): pregunta qué comió 2-3 horas antes y si se aplicó glulisina
  * Si hay hipoglucemia (<70): pregunta si ya comió algo y cuándo fue la última dosis de insulina
  * Si hay alta variabilidad (CV>36%): pregunta sobre estrés, actividad física o cambios de rutina
  * Si pregunta sobre dosis: responde basándote en su esquema actual (degludec 40 UI basal + glulisina 20/20/18 UI + metformina 850 mg) pero SIEMPRE recuerda confirmar con su médico tratante
- Usa emojis con moderación para hacer el mensaje amigable (1-2 por respuesta)
- Si detectas una situación potencialmente peligrosa (hipo severa, hiper sostenida), indícalo con urgencia clara
"""

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context_message},
            {"role": "assistant", "content": "Entendido. Tengo acceso al perfil clínico completo y al historial glucémico del CGM. ¿En qué puedo ayudarte?"},
        ]

        # Agregar historial de conversacion previo
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Agregar la pregunta actual
        messages.append({"role": "user", "content": question})

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            max_completion_tokens=1500,
        )

        return response.choices[0].message.content or ""

    def summarize_conversation(self, messages: list[dict]) -> str:
        """
        Resume un batch de mensajes preservando todos los hechos clínicos relevantes.
        Diseñado para no perder información sobre cambios que la paciente reportó
        (ej. "no compré la metformina", "cambié la dosis").
        """
        formatted = "\n".join(
            f"[{m['role'].upper()}]: {m['content']}" for m in messages
        )

        user_message = f"""
Resume la siguiente conversación entre la paciente/cuidador y el asistente médico.

CONVERSACIÓN:
{formatted}

INSTRUCCIONES CRÍTICAS PARA EL RESUMEN:
- Preserva TODOS los hechos que la paciente mencionó sobre su tratamiento actual
- Anota EXPLÍCITAMENTE si la paciente dijo que NO está tomando algún medicamento
- Incluye cualquier cambio de dosis reportado por la paciente (aunque sea por cuenta propia)
- Registra síntomas nuevos, episodios hipoglucémicos o hiperglucémicos relevantes discutidos
- Menciona las recomendaciones dadas por el asistente y si la paciente las aceptó
- Incluye patrones glucémicos discutidos y sus posibles causas identificadas
- Máximo 300 palabras. Formato narrativo claro.
"""

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=600,
        )

        return response.choices[0].message.content or ""

    def extract_patient_notes(self, messages: list[dict]) -> list[dict]:
        """
        Extrae hechos clínicos que la paciente mencionó explícitamente y que
        pueden diferir del perfil clínico base (patient_profile.json).

        Retorna lista de {"content": "...", "type": "medication|correction|symptom|behavior"}.
        Solo incluye hechos mencionados explícitamente por la paciente — no inferencias.
        """
        formatted = "\n".join(
            f"[{m['role'].upper()}]: {m['content']}" for m in messages
        )

        user_message = f"""
Analiza esta conversación y extrae SOLO los hechos que la PACIENTE reportó
explícitamente y que podrían diferir del perfil clínico base.

CONVERSACIÓN:
{formatted}

Busca específicamente:
- Medicamentos que NO está tomando o que dejó de tomar (ej: "no compré la metformina")
- Cambios en dosis que ella hizo por cuenta propia (ej: "me puse 18 en vez de 20")
- Síntomas nuevos o persistentes que reportó
- Cambios en rutina, alimentación o actividad física clínicamente relevantes
- Cualquier corrección a información del perfil clínico

Retorna JSON:
{{"notes": [
    {{"content": "descripción clara y fechada del hecho", "type": "medication|correction|symptom|behavior"}},
    ...
]}}

Si no hay hechos relevantes, retorna {{"notes": []}}.
IMPORTANTE: solo incluye hechos mencionados EXPLÍCITAMENTE por la paciente, no inferencias del asistente.
"""

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=500,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or '{"notes": []}'
        try:
            result = json.loads(content)
            return result.get("notes", [])
        except json.JSONDecodeError:
            logger.warning("extract_patient_notes: respuesta JSON inválida")
            return []

    def detect_patterns(self, weekly_data: list[dict[str, Any]]) -> list[str]:
        """
        Analiza una semana de datos para detectar patrones clínicos recurrentes.
        """
        user_message = f"""
        Analiza los datos de glucosa de los últimos 7 días y detecta patrones clínicos:

        {json.dumps(weekly_data, ensure_ascii=False, indent=2)}

        Lista los patrones detectados en formato JSON:
        {{"patterns": ["descripción concreta del patrón 1", "patrón 2", ...]}}

        Enfócate en: fenómeno del amanecer, hipoglucemia nocturna, picos post-prandiales,
        variabilidad por día de la semana, tendencias preocupantes.
        """

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=500,

            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or '{"patterns": []}'
        result = json.loads(content)
        return result.get("patterns", [])
