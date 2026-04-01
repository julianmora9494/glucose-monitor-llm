#!/usr/bin/env python3
"""
Script de diagnóstico para Azure OpenAI.
Verifica: credenciales, conexión de red, y capacidad de hacer una llamada.
"""

import os
import sys
from pathlib import Path

# Cargar variables de entorno
from dotenv import load_dotenv

load_dotenv()

# Verificar variables requeridas
required_vars = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
]

print("=" * 60)
print("VERIFICACIÓN AZURE OPENAI")
print("=" * 60)

missing = []
for var in required_vars:
    value = os.getenv(var)
    if not value:
        missing.append(var)
        print(f"❌ {var}: NO CONFIGURADO")
    else:
        # Mostrar valores parcialmente ocultados
        if var == "AZURE_OPENAI_API_KEY":
            display = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
        else:
            display = value
        print(f"✓ {var}: {display}")

if missing:
    print(f"\n❌ Faltan variables de entorno: {', '.join(missing)}")
    print("   Actualiza .env con los valores correctos.")
    sys.exit(1)

print("\n" + "-" * 60)
print("Intentando conexión...")
print("-" * 60)

try:
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )

    print("✓ Cliente AzureOpenAI inicializado")

    # Hacer una llamada simple para verificar
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {"role": "user", "content": "Responde 'OK' en una palabra."}
        ],
        max_completion_tokens=10,
    )

    print("✓ Llamada a API exitosa")
    print(f"\nRespuesta: {response.choices[0].message.content}")

    print("\n" + "=" * 60)
    print("✓ CONEXIÓN EXITOSA")
    print("=" * 60)

except Exception as e:
    print(f"\n❌ ERROR: {type(e).__name__}")
    print(f"   {str(e)}")
    print("\nDiagnóstico:")

    error_msg = str(e).lower()
    if "auth" in error_msg or "invalid" in error_msg:
        print("   → Problema de autenticación. Verifica AZURE_OPENAI_API_KEY")
    elif "endpoint" in error_msg or "404" in error_msg:
        print("   → Problema de endpoint. Verifica AZURE_OPENAI_ENDPOINT")
    elif "deployment" in error_msg:
        print("   → Problema de deployment. Verifica AZURE_OPENAI_DEPLOYMENT")
    elif "connection" in error_msg or "timeout" in error_msg:
        print("   → Problema de red. Verifica conectividad a internet")

    sys.exit(1)
