# Historial Clínico — María Verónica López Falla

> ⚠️ **AVISO DE PRIVACIDAD**: Esta carpeta contiene información médica sensible (PHI).
> Los archivos raw en `uploads/` están en `.gitignore` y NUNCA se suben a GitHub.
> Solo se sube a git el código de procesamiento y los datos estructurados no identificables.

---

## Estructura

```
clinical_history/
├── uploads/          ← Pon aquí los archivos RAW (gitignored, solo local)
│   ├── chatgpt_export/      # Export de ChatGPT (ver instrucciones abajo)
│   ├── examenes/            # PDFs de exámenes de laboratorio
│   └── notas_medicas/       # Notas del médico, recetas, etc.
├── processed/        ← Datos estructurados procesados (pueden ir a git si son anonimizados)
│   ├── patient_profile.json         # Perfil clínico base
│   ├── medications.json             # Medicamentos actuales
│   ├── lab_results.json             # Resultados de laboratorio históricos
│   └── medical_notes.md             # Notas consolidadas
└── scripts/          ← Scripts para procesar los archivos raw
    ├── process_chatgpt_export.py    # Extrae info médica del export de ChatGPT
    └── process_lab_pdf.py           # Extrae datos de PDFs de exámenes
```

---

## Dónde poner PDFs, imágenes y exámenes

```
clinical_history/uploads/
├── examenes/           ← PDFs e imágenes de exámenes de laboratorio
│   ├── hemograma_2026-03.pdf
│   ├── lipidos_2026-03.jpg
│   └── ...
├── formulas/           ← Fórmulas médicas (insulina, metformina, etc.)
│   └── formula_diabetes_2026-03-13.pdf
└── notas_medicas/      ← Notas de consulta, órdenes, remisiones
    └── ginecologia_2026-03-18.pdf
```

Después de poner los archivos, el LLM los puede procesar con Azure OpenAI (GPT-4o Vision para imágenes y PDFs).

> Todos los archivos en `uploads/` están en `.gitignore` — nunca van a GitHub.

---

## Cómo exportar tu historial de ChatGPT

1. Ve a **ChatGPT** → tu avatar (esquina superior derecha) → **Settings**
2. Sección **Data controls** → **Export data**
3. Recibirás un email con un link de descarga (puede tardar unos minutos)
4. Descarga el `.zip` y descomprímelo
5. Encontrarás `conversations.json` — ese es el archivo principal
6. Copia el contenido en `clinical_history/uploads/chatgpt_export/`
7. Ejecuta: `python clinical_history/scripts/process_chatgpt_export.py`

---

## Cómo agregar exámenes de laboratorio (PDFs)

1. Copia los PDFs de exámenes a `clinical_history/uploads/examenes/`
2. Ejecuta: `python clinical_history/scripts/process_lab_pdf.py`
3. Los datos estructurados quedarán en `clinical_history/processed/lab_results.json`

---

## Perfil clínico de la paciente

El LLM usa `processed/patient_profile.json` como contexto para personalizar
interpretaciones y recomendaciones. Actualiza este archivo con:

- Diagnóstico principal y fecha
- Tipo de diabetes (1, 2, MODY, etc.)
- Medicamentos actuales y dosis
- Comorbilidades
- Metas glucémicas acordadas con el médico
- Alergias y contraindicaciones
- Historia de hipoglucemias severas

---

## Uso por el LLM (Azure OpenAI)

El sistema carga automáticamente `processed/patient_profile.json` y
`processed/medications.json` como contexto del sistema en cada llamada al LLM,
permitiendo interpretaciones personalizadas del control glucémico.
