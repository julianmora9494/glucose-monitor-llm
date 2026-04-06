"""
Formateadores de mensajes para Telegram.
Convierte respuestas de la API en texto legible con emojis.
"""

from typing import Optional

# Límite de caracteres por mensaje de Telegram
TELEGRAM_MAX_LEN = 4096


def _status_icon(value: float, ok_threshold: float, warn_threshold: float, higher_is_worse: bool) -> str:
    """Retorna un emoji según el nivel de la métrica respecto a los umbrales."""
    if higher_is_worse:
        if value <= ok_threshold:
            return "✅"
        elif value <= warn_threshold:
            return "⚠️"
        else:
            return "🔴"
    else:
        if value >= ok_threshold:
            return "✅"
        elif value >= warn_threshold:
            return "⚠️"
        else:
            return "🔴"


def format_status(reading: dict) -> str:
    """
    Formatea la última lectura glucémica como mensaje de Telegram.
    Incluye valor, tendencia, tiempo transcurrido y nivel de alerta.
    """
    glucose = reading.get("glucose_mgdl", 0)
    trend_desc = reading.get("trend_description", "sin tendencia")
    minutes_ago = reading.get("minutes_ago", 0)
    alert_level = reading.get("alert_level", "ok")
    range_label = reading.get("range_label", "")

    # Emoji según nivel de alerta
    if alert_level == "critical":
        alert_emoji = "🆘"
    elif alert_level == "warning":
        alert_emoji = "⚠️"
    else:
        alert_emoji = "✅"

    # Emoji según tendencia
    trend_emoji = ""
    if trend_desc:
        td = trend_desc.lower()
        if "rápido" in td and "subiendo" in td:
            trend_emoji = "⬆️⬆️"
        elif "subiendo" in td:
            trend_emoji = "↗️"
        elif "rápido" in td and "bajando" in td:
            trend_emoji = "⬇️⬇️"
        elif "bajando" in td:
            trend_emoji = "↘️"
        else:
            trend_emoji = "➡️"

    # Tiempo transcurrido
    if minutes_ago < 2:
        time_str = "ahora mismo"
    else:
        time_str = f"hace {int(minutes_ago)} min"

    lines = [
        f"{alert_emoji} *Glucosa actual*",
        f"📊 {glucose:.0f} mg/dL {trend_emoji}",
        f"🏷 {range_label} — {trend_desc}",
        f"🕐 Lectura {time_str}",
    ]

    return "\n".join(lines)


def format_daily_summary(summary: dict) -> str:
    """
    Formatea el resumen AGP diario con métricas clínicas.
    Reutiliza el patrón de iconos del monitor.
    """
    date_str = summary.get("date", "hoy")
    tir = summary.get("tir_percent", 0)
    tar = summary.get("tar_percent", 0)
    tbr = summary.get("tbr_percent", 0)
    tbr_severe = summary.get("tbr_severe_percent", 0)
    cv = summary.get("cv_percent", 0)
    gmi = summary.get("gmi_percent", 0)
    avg = summary.get("avg_glucose_mgdl", 0)
    min_g = summary.get("min_glucose_mgdl", 0)
    max_g = summary.get("max_glucose_mgdl", 0)
    count = summary.get("reading_count", 0)
    hypo = summary.get("hypo_episodes", 0)
    hyper = summary.get("hyper_episodes", 0)
    mage = summary.get("mage_mgdl")

    tir_icon = _status_icon(tir, ok_threshold=70, warn_threshold=50, higher_is_worse=False)
    tar_icon = _status_icon(tar, ok_threshold=25, warn_threshold=40, higher_is_worse=True)
    tbr_icon = _status_icon(tbr, ok_threshold=4, warn_threshold=8, higher_is_worse=True)
    cv_icon = _status_icon(cv, ok_threshold=36, warn_threshold=45, higher_is_worse=True)
    gmi_icon = _status_icon(gmi, ok_threshold=7.0, warn_threshold=8.0, higher_is_worse=True)

    lines = [
        f"📊 *Resumen glucémico — {date_str}*",
        "",
        f"{tir_icon} TIR: {tir:.1f}%  (objetivo >70%)",
        f"{tar_icon} TAR: {tar:.1f}%  (objetivo <25%)",
        f"{tbr_icon} TBR: {tbr:.1f}%  (objetivo <4%)",
    ]

    if tbr_severe > 0:
        tbr_severe_icon = _status_icon(tbr_severe, ok_threshold=1, warn_threshold=2, higher_is_worse=True)
        lines.append(f"{tbr_severe_icon} TBR severo: {tbr_severe:.1f}%  (objetivo <1%)")

    lines += [
        f"{cv_icon} CV:  {cv:.1f}%  (objetivo <36%)",
        f"{gmi_icon} GMI: {gmi:.1f}%  (HbA1c estimada)",
        "",
        f"📈 Promedio: {avg:.0f} mg/dL",
        f"📉 Min/Max: {min_g:.0f} / {max_g:.0f} mg/dL",
    ]

    if mage is not None:
        lines.append(f"〰️ MAGE: {mage:.0f} mg/dL  (objetivo <140)")

    lines += [
        f"🔢 Lecturas: {count}",
        f"⚡ Episodios — hipo: {hypo} | hiper: {hyper}",
    ]

    return "\n".join(lines)


def format_weekly_summary(summary: dict) -> str:
    """
    Formatea el resumen semanal de métricas AGP.
    """
    week_start = summary.get("week_start", "")
    week_end = summary.get("week_end", "")
    days = summary.get("days_with_data", 0)
    avg_tir = summary.get("avg_tir_percent", 0)
    avg_glucose = summary.get("avg_glucose_mgdl", 0)
    avg_cv = summary.get("avg_cv_percent", 0)
    gmi = summary.get("gmi_percent", 0)
    total_hypo = summary.get("total_hypo_episodes", 0)
    total_hyper = summary.get("total_hyper_episodes", 0)

    tir_icon = _status_icon(avg_tir, ok_threshold=70, warn_threshold=50, higher_is_worse=False)
    cv_icon = _status_icon(avg_cv, ok_threshold=36, warn_threshold=45, higher_is_worse=True)
    gmi_icon = _status_icon(gmi, ok_threshold=7.0, warn_threshold=8.0, higher_is_worse=True)

    lines = [
        f"📅 *Resumen semanal* ({week_start} → {week_end})",
        f"📆 Días con datos: {days}",
        "",
        f"{tir_icon} TIR promedio: {avg_tir:.1f}%",
        f"📈 Glucosa promedio: {avg_glucose:.0f} mg/dL",
        f"{cv_icon} CV promedio: {avg_cv:.1f}%",
        f"{gmi_icon} GMI: {gmi:.1f}%",
        "",
        f"⚡ Episodios totales — hipo: {total_hypo} | hiper: {total_hyper}",
    ]

    # Detalle por día si hay datos individuales
    daily_list: list[dict] = summary.get("days", [])
    if daily_list:
        lines.append("")
        lines.append("*Detalle por día:*")
        for day in daily_list[-7:]:  # Máximo 7 días
            d_tir = day.get("tir_percent", 0)
            d_icon = _status_icon(d_tir, ok_threshold=70, warn_threshold=50, higher_is_worse=False)
            lines.append(
                f"{d_icon} {day.get('date', '')}: TIR {d_tir:.0f}% | "
                f"avg {day.get('avg_glucose_mgdl', 0):.0f} mg/dL"
            )

    return "\n".join(lines)


def format_help() -> str:
    """Mensaje de ayuda con la lista de comandos disponibles."""
    return (
        "🩺 *Bot de Monitoreo Glucémico*\n"
        "\n"
        "*Comandos disponibles:*\n"
        "/status — Lectura actual + tendencia\n"
        "/resumen — Resumen AGP de hoy\n"
        "/semana — Resumen de los últimos 7 días\n"
        "/limpiar — Reiniciar conversación con la IA\n"
        "/ayuda — Esta ayuda\n"
        "\n"
        "💬 También puedes escribir cualquier pregunta directamente y la IA médica responderá "
        "con base en tu historial glucémico completo.\n"
        "\n"
        "_Ejemplos: '¿Cuánta insulina me aplico?', '¿Cómo estuvo mi glucosa esta semana?', "
        "'¿Por qué subí tanto después del almuerzo?'_"
    )


def split_message(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list[str]:
    """
    Divide un texto largo en fragmentos aptos para Telegram (máx 4096 chars).
    Intenta dividir en saltos de línea para no cortar palabras.
    """
    if len(text) <= max_len:
        return [text]

    parts: list[str] = []
    while len(text) > max_len:
        # Buscar el último salto de línea dentro del límite
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            # No hay salto de línea: cortar en el límite
            split_at = max_len

        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    if text:
        parts.append(text)

    return parts


def format_api_error(detail: Optional[str] = None) -> str:
    """Mensaje de error amigable cuando la API no responde."""
    msg = "❌ No pude obtener los datos en este momento."
    if detail:
        msg += f"\n_{detail}_"
    msg += "\nVerifica que el servicio esté activo e intenta de nuevo."
    return msg
