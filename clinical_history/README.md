# Historial Clínico — Instrucciones

> ⚠️ **PRIVACIDAD**: Todo el contenido de esta carpeta es PHI (datos médicos sensibles).
> Está completamente en `.gitignore`. **Nada aquí llega a GitHub.**
> Los archivos solo existen en tu máquina local.

---

## Dónde poner cada tipo de archivo

```
clinical_history/
├── uploads/
│   ├── examenes/        ← PDFs o fotos de resultados de laboratorio
│   ├── formulas/        ← Fórmulas médicas (insulina, otros medicamentos)
│   ├── notas_medicas/   ← Notas de consulta, remisiones, órdenes
│   └── chatgpt_export/  ← Export de ChatGPT (conversations.json)
└── processed/
    ├── patient_profile.json   ← Perfil clínico base (editable manualmente)
    └── medical_notes.md       ← Notas consolidadas del historial
```

---

## Cómo agregar nuevos datos

### Opción 1 — Pegar texto en el chat con Claude (más rápido)
Si tienes un resultado de laboratorio o nota médica, simplemente **pégalo en el chat**.
Claude lo procesa y actualiza `patient_profile.json` automáticamente.

### Opción 2 — Subir PDF o imagen
1. Copia el archivo a `clinical_history/uploads/examenes/` (o la carpeta correspondiente)
2. Díselo a Claude: _"Subí el examen de colesterol a clinical_history/uploads/examenes/"_
3. Claude lo leerá con Azure OpenAI Vision y extraerá los datos

### Opción 3 — Editar manualmente
Abre `clinical_history/processed/patient_profile.json` y edita directamente.

---

## Datos pendientes de agregar (próximas consultas)

Cuando tengas esta información, agrégala con cualquier de las opciones anteriores:

| Dato | Estado |
|------|--------|
| Nombre exacto de la insulina rápida | ⏳ Pendiente |
| Dosis de levotiroxina | ⏳ Pendiente |
| Resultado de prolactina | ⏳ Pendiente |
| Resultado de VIH 1 y 2 | ⏳ Pendiente |
| Resultado de Hepatitis B (HBsAg) | ⏳ Pendiente |
| Resultado de Treponema pallidum IgG (sífilis) | ⏳ Pendiente |
| Relación albúmina/creatinina en orina | ⏳ Pendiente |
| Registro de glucosas 3-7 días del Libre (pantallazos) | ⏳ Pendiente |

---

## Cómo exportar el historial de ChatGPT (si necesitas el resto de conversaciones)

1. ChatGPT → avatar (esquina superior derecha) → **Settings**
2. **Data controls** → **Export data** → confirmar
3. Recibirás un email con un ZIP (puede tardar unos minutos)
4. Descomprimir → copiar `conversations.json` a `clinical_history/uploads/chatgpt_export/`
5. Ejecutar: `python clinical_history/scripts/process_chatgpt_export.py`
