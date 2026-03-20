"""
Script para procesar el export de ChatGPT y extraer información clínica relevante.

Uso:
    python clinical_history/scripts/process_chatgpt_export.py \
        --input clinical_history/uploads/chatgpt_export/conversations.json \
        --output clinical_history/processed/
"""

import json
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Any


# Palabras clave médicas para filtrar conversaciones relevantes
MEDICAL_KEYWORDS: list[str] = [
    "glucosa", "glucose", "diabetes", "insulina", "insulin",
    "hemoglobina", "hba1c", "a1c", "metformina", "glibenclamida",
    "hipoglucemia", "hiperglucemia", "páncreas", "endocrinólogo",
    "mg/dl", "mmol", "libre link", "freestyle", "cgm", "sensor",
    "dosis", "medicamento", "examen", "laboratorio", "resultado",
    "colesterol", "triglicéridos", "presión arterial", "hemograma",
    "creatinina", "filtrado glomerular", "microalbúmina",
    "retinopatía", "neuropatía", "nefropatía", "pie diabético"
]


def is_medical_conversation(messages: list[dict[str, Any]]) -> bool:
    """Determina si una conversacion es medicamente relevante."""
    text = " ".join(
        msg.get("content", "") if isinstance(msg.get("content"), str) else ""
        for msg in messages
    ).lower()
    return any(keyword in text for keyword in MEDICAL_KEYWORDS)


def extract_medical_insights(conversations: list[dict[str, Any]]) -> dict[str, Any]:
    """Extrae información médica relevante de las conversaciones."""
    medical_convs = []

    for conv in conversations:
        title = conv.get("title", "")
        messages = []

        # El formato de ChatGPT export tiene "mapping" con nodos
        mapping = conv.get("mapping", {})
        for node_id, node in mapping.items():
            message = node.get("message")
            if message and message.get("content"):
                content = message["content"]
                # El content puede ser string o dict con parts
                if isinstance(content, dict):
                    parts = content.get("parts", [])
                    text = " ".join(str(p) for p in parts if isinstance(p, str))
                elif isinstance(content, str):
                    text = content
                else:
                    continue

                if text.strip():
                    messages.append({
                        "role": message.get("author", {}).get("role", "unknown"),
                        "content": text,
                        "create_time": message.get("create_time")
                    })

        if messages and is_medical_conversation(messages):
            medical_convs.append({
                "title": title,
                "create_time": conv.get("create_time"),
                "update_time": conv.get("update_time"),
                "message_count": len(messages),
                "messages": messages
            })

    return {
        "total_conversations": len(conversations),
        "medical_conversations_found": len(medical_convs),
        "extracted_at": datetime.now().isoformat(),
        "conversations": medical_convs
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Procesa el export de ChatGPT para extraer información médica"
    )
    parser.add_argument(
        "--input",
        default="clinical_history/uploads/chatgpt_export/conversations.json",
        help="Ruta al archivo conversations.json del export de ChatGPT"
    )
    parser.add_argument(
        "--output",
        default="clinical_history/processed/",
        help="Directorio de salida para los archivos procesados"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[ERROR] No se encontró el archivo: {input_path}")
        print("[INFO] Exporta tu historial de ChatGPT siguiendo las instrucciones en clinical_history/README.md")
        return

    print(f"[INFO] Leyendo {input_path}...")
    with open(input_path, encoding="utf-8") as f:
        conversations = json.load(f)

    print(f"[INFO] Total de conversaciones encontradas: {len(conversations)}")

    insights = extract_medical_insights(conversations)

    output_path = output_dir / "chatgpt_medical_history.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=2)

    print(f"[OK] Conversaciones médicas extraídas: {insights['medical_conversations_found']}")
    print(f"[OK] Guardado en: {output_path}")
    print()
    print("Próximo paso: revisar el archivo y actualizar clinical_history/processed/patient_profile.json")


if __name__ == "__main__":
    main()
