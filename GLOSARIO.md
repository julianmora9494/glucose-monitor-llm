# Glosario de términos médicos — Glucose Intelligence Platform

> Para Verónica y su cuidador: explicación en lenguaje simple de cada indicador que muestra el sistema.

---

## Los 5 indicadores principales (aparecen en el resumen diario)

---

### ✅ TIR — Tiempo en Rango
**Qué es:** El porcentaje del día que la glucosa estuvo entre 70 y 180 mg/dL (el rango "sano").
**En palabras simples:** De todas las horas del día, ¿cuánto tiempo estuvo la glucosa donde debería estar?

| Resultado | Qué significa |
|-----------|--------------|
| >70% ✅ | Buen control — la glucosa estuvo en rango más de 17 horas del día |
| 50–70% ⚠️ | Control regular — hay margen de mejora |
| <50% 🔴 | Control bajo — conviene revisar con el médico |

**Ejemplo:** TIR 72% = de 24 horas, la glucosa estuvo en rango ~17 horas. ✅

---

### 🔴 TAR — Tiempo Por Encima del Rango
**Qué es:** El porcentaje del día que la glucosa estuvo **alta** (por encima de 180 mg/dL).
**En palabras simples:** ¿Cuánto tiempo estuvo la glucosa demasiado alta?

| Resultado | Qué significa |
|-----------|--------------|
| <25% ✅ | Bien — menos de 6 horas del día con glucosa alta |
| 25–40% ⚠️ | Regular — hay episodios de hiperglucemia frecuentes |
| >40% 🔴 | Preocupante — la glucosa pasa mucho tiempo alta |

**Por qué importa:** Glucosa alta por mucho tiempo daña los vasos sanguíneos y los riñones a largo plazo.

---

### 🟡 TBR — Tiempo Por Debajo del Rango
**Qué es:** El porcentaje del día que la glucosa estuvo **baja** (por debajo de 70 mg/dL = hipoglucemia).
**En palabras simples:** ¿Cuánto tiempo estuvo la glucosa peligrosamente baja?

| Resultado | Qué significa |
|-----------|--------------|
| <4% ✅ | Bien — menos de 1 hora del día con hipoglucemia |
| 4–8% ⚠️ | Regular — hay hipoglucemias frecuentes |
| >8% 🔴 | Preocupante — demasiadas hipoglucemias |

**Por qué importa:** La hipoglucemia es la emergencia más inmediata en diabetes. Puede causar mareo, temblor, confusión y en casos graves pérdida del conocimiento.

---

### 📊 CV — Coeficiente de Variación
**Qué es:** Qué tan "estable" o "montañosa" estuvo la glucosa durante el día.
**En palabras simples:** ¿Sube y baja mucho la glucosa o se mantiene relativamente estable?

| Resultado | Qué significa |
|-----------|--------------|
| <36% ✅ | Glucosa estable — subidas y bajadas moderadas |
| 36–45% ⚠️ | Glucosa variable — oscilaciones frecuentes |
| >45% 🔴 | Glucosa muy inestable — muchos picos y valles |

**Por qué importa:** Una glucosa que sube y baja mucho (aunque el promedio sea "normal") es señal de que el control no es óptimo y aumenta el riesgo de hipoglucemias.

---

### 🧮 GMI — Indicador de Manejo de Glucosa (HbA1c estimada)
**Qué es:** Una estimación de la HbA1c (hemoglobina glicosilada) calculada desde el sensor.
**En palabras simples:** Es como un "promedio de los últimos días" que el médico usa para evaluar el control general. No reemplaza el examen de laboratorio, pero da una idea.

| Resultado | Qué significa |
|-----------|--------------|
| <7.0% ✅ | Buen control glucémico general |
| 7.0–8.0% ⚠️ | Control regular — el médico puede sugerir ajustes |
| >8.0% 🔴 | Control insuficiente — importante revisar con el médico |

**La HbA1c real de Verónica:** 7.82% (último examen). El GMI del sensor debe ir acercándose a ese número con mejor control.

---

## Otros términos que aparecen en el sistema

---

### Hipoglucemia
**Glucosa por debajo de 70 mg/dL.**
Síntomas: temblor, sudoración, hambre súbita, mareo, visión borrosa, confusión.
Acción: tomar azúcar (jugo, glucosa, dulce) de inmediato y medir en 15 minutos.

**Hipoglucemia severa:** glucosa por debajo de 54 mg/dL — requiere atención urgente.

---

### Hiperglucemia
**Glucosa por encima de 180 mg/dL** después de comer, o más de 130 mg/dL en ayunas.
Síntomas: sed excesiva, ganas de orinar, cansancio, visión borrosa.
Acción: revisar si faltó insulina, si hubo comida abundante, o si hay estrés/enfermedad.

---

### TBR Severo
Tiempo con glucosa por debajo de **54 mg/dL** (hipoglucemia grave).
Objetivo: menos del 1% del día (menos de ~15 minutos). Cualquier tiempo aquí es preocupante.

---

### MAGE — Amplitud Media de Excursiones Glucémicas
**Qué es:** El tamaño promedio de las "montañas y valles" de glucosa durante el día.
**En palabras simples:** Qué tan grandes son los picos y caídas.
Objetivo: menos de 140 mg/dL. Valores altos indican glucemia muy inestable.

---

### Insulina Basal (Degludec 40 UI)
La insulina de "fondo" que actúa todo el día. Le da una cobertura base constante de 24 horas.
No sube ni baja la glucosa rápido — es el "piso" del tratamiento.

### Insulina Rápida (20-20-18 UI)
La insulina que se aplica antes de cada comida. Cubre el aumento de glucosa por los alimentos.
La dosis de 20/20/18 puede ajustarse (titular) según la glucemia antes de comer.

---

## Umbrales configurados en el sistema de alertas

| Umbral | Valor | Tipo de alerta |
|--------|-------|---------------|
| Hipoglucemia severa | < 55 mg/dL | 🆘 Crítica |
| Hipoglucemia | < 70 mg/dL | 🚨 Alta |
| Hiperglucemia | > 180 mg/dL | 🚨 Alta |
| Hiperglucemia severa | > 250 mg/dL | 🆘 Crítica |
| Caída rápida | > 2 mg/dL por minuto | 📉 Tendencia |
| Subida rápida | > 2 mg/dL por minuto | 📈 Tendencia |

---

## ¿Cada cuánto se mide?

El sensor FreeStyle Libre 2 Plus mide glucosa cada **minuto**, pero el sistema consulta la API de LibreLinkUp cada **2 minutos** para no sobrecargar el servidor.

---

*Este glosario es solo para entender mejor los datos. Siempre consultar con el médico tratante cualquier duda clínica.*
