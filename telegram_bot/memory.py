"""
Persistencia de conversaciones del bot en DuckDB (conversations.duckdb).

Archivo separado de glucose.duckdb — el bot es el único writer, sin conflictos.

Tres niveles de memoria:
  - conversation_messages : mensajes crudos user/assistant
  - conversation_summaries: resúmenes LLM de períodos >7 días
  - patient_notes         : hechos que Veronica mencionó que pueden contradecir el perfil clínico
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import duckdb

logger = logging.getLogger(__name__)

# Ruta del archivo DuckDB de conversaciones (separado del de glucosa)
CONVERSATIONS_DB_PATH = "data/conversations.duckdb"

# Mensajes más recientes que RECENT_DAYS se incluyen verbatim en el contexto LLM
RECENT_DAYS = 7
# Máximo de mensajes recientes a incluir para no saturar el contexto
MAX_RECENT_MESSAGES = 40


class ConversationStore:
    """
    Persiste mensajes, resúmenes y notas de la paciente en DuckDB.

    El bot es el único proceso que escribe en este archivo — no hay
    conflictos de single-writer con glucose.duckdb (que es propiedad de la API).
    """

    def __init__(self, db_path: str = CONVERSATIONS_DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        """Conexión read-write al archivo de conversaciones."""
        return duckdb.connect(self.db_path)

    def _initialize_schema(self) -> None:
        """Crea tablas y secuencias si no existen. Idempotente."""
        con = self._connect()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id          INTEGER PRIMARY KEY,
                    chat_id     BIGINT NOT NULL,
                    role        VARCHAR NOT NULL,
                    content     TEXT NOT NULL,
                    timestamp   TIMESTAMPTZ NOT NULL
                )
            """)
            con.execute("CREATE SEQUENCE IF NOT EXISTS msg_id_seq START 1")

            con.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id              INTEGER PRIMARY KEY,
                    chat_id         BIGINT NOT NULL,
                    period_start    TIMESTAMPTZ NOT NULL,
                    period_end      TIMESTAMPTZ NOT NULL,
                    summary         TEXT NOT NULL,
                    message_count   INTEGER NOT NULL,
                    created_at      TIMESTAMPTZ NOT NULL
                )
            """)
            con.execute("CREATE SEQUENCE IF NOT EXISTS summary_id_seq START 1")

            con.execute("""
                CREATE TABLE IF NOT EXISTS patient_notes (
                    id          INTEGER PRIMARY KEY,
                    chat_id     BIGINT NOT NULL,
                    content     TEXT NOT NULL,
                    note_type   VARCHAR,
                    source_date DATE,
                    is_active   BOOLEAN DEFAULT TRUE,
                    created_at  TIMESTAMPTZ NOT NULL
                )
            """)
            con.execute("CREATE SEQUENCE IF NOT EXISTS note_id_seq START 1")
        finally:
            con.close()

    # ──────────────────────────────────────────────────────────────────────────
    # Mensajes
    # ──────────────────────────────────────────────────────────────────────────

    def save_message(
        self,
        chat_id: int,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Persiste un mensaje (user o assistant) en la DB."""
        ts = timestamp or datetime.now(timezone.utc)
        con = self._connect()
        try:
            next_id = con.execute("SELECT nextval('msg_id_seq')").fetchone()[0]
            con.execute(
                "INSERT INTO conversation_messages VALUES (?, ?, ?, ?, ?)",
                [next_id, chat_id, role, content, ts],
            )
        finally:
            con.close()

    def get_recent_messages(
        self,
        chat_id: int,
        since: Optional[datetime] = None,
        days: int = RECENT_DAYS,
        max_count: int = MAX_RECENT_MESSAGES,
    ) -> list[dict]:
        """
        Retorna los últimos N mensajes de los últimos X días, en orden cronológico.

        Args:
            since: si el usuario hizo /limpiar, solo incluir mensajes posteriores a esa fecha.
        """
        cutoff = since or (datetime.now(timezone.utc) - timedelta(days=days))
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT role, content, timestamp
                FROM conversation_messages
                WHERE chat_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, [chat_id, cutoff, max_count]).fetchall()
            # Invertir para que queden en orden cronológico
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
        finally:
            con.close()

    def get_messages_to_summarize(self, chat_id: int) -> list[dict]:
        """
        Retorna los mensajes más antiguos que RECENT_DAYS que aún no están
        cubiertos por ningún resumen existente.
        """
        older_than = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
        con = self._connect()
        try:
            # Hasta dónde llega la cobertura de resúmenes existentes
            row = con.execute("""
                SELECT MAX(period_end)
                FROM conversation_summaries
                WHERE chat_id = ?
            """, [chat_id]).fetchone()
            last_covered = row[0] if row and row[0] else datetime.min.replace(tzinfo=timezone.utc)

            rows = con.execute("""
                SELECT role, content, timestamp
                FROM conversation_messages
                WHERE chat_id = ?
                  AND timestamp < ?
                  AND timestamp > ?
                ORDER BY timestamp ASC
            """, [chat_id, older_than, last_covered]).fetchall()

            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
        finally:
            con.close()

    # ──────────────────────────────────────────────────────────────────────────
    # Resúmenes
    # ──────────────────────────────────────────────────────────────────────────

    def save_summary(
        self,
        chat_id: int,
        period_start: datetime,
        period_end: datetime,
        summary: str,
        message_count: int,
    ) -> None:
        """Persiste un resumen generado por el LLM."""
        con = self._connect()
        try:
            next_id = con.execute("SELECT nextval('summary_id_seq')").fetchone()[0]
            now = datetime.now(timezone.utc)
            con.execute(
                "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?)",
                [next_id, chat_id, period_start, period_end, summary, message_count, now],
            )
        finally:
            con.close()

    def get_summaries(self, chat_id: int) -> list[dict]:
        """Retorna todos los resúmenes del chat_id, en orden cronológico."""
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT period_start, period_end, summary, message_count
                FROM conversation_summaries
                WHERE chat_id = ?
                ORDER BY period_start ASC
            """, [chat_id]).fetchall()
            return [
                {
                    "period_start": r[0],
                    "period_end": r[1],
                    "summary": r[2],
                    "message_count": r[3],
                }
                for r in rows
            ]
        finally:
            con.close()

    # ──────────────────────────────────────────────────────────────────────────
    # Notas de la paciente
    # ──────────────────────────────────────────────────────────────────────────

    def save_notes(
        self,
        chat_id: int,
        notes: list[dict],
        source_date: Optional[datetime] = None,
    ) -> None:
        """
        Persiste las notas clínicas extraídas por el LLM.

        Args:
            notes: lista de {"content": "...", "type": "medication|correction|symptom|behavior"}
            source_date: fecha de referencia de los mensajes origen.
        """
        if not notes:
            return
        ref_date = (source_date or datetime.now(timezone.utc)).date()
        con = self._connect()
        try:
            now = datetime.now(timezone.utc)
            for note in notes:
                content = note.get("content", "").strip()
                if not content:
                    continue
                next_id = con.execute("SELECT nextval('note_id_seq')").fetchone()[0]
                con.execute(
                    "INSERT INTO patient_notes VALUES (?, ?, ?, ?, ?, TRUE, ?)",
                    [next_id, chat_id, content, note.get("type"), ref_date, now],
                )
            logger.info("Guardadas %d notas de paciente para chat_id=%s", len(notes), chat_id)
        finally:
            con.close()

    def get_active_notes(self, chat_id: int) -> list[dict]:
        """Retorna las notas activas de la paciente (pueden contradecir el perfil clínico)."""
        con = self._connect()
        try:
            rows = con.execute("""
                SELECT content, note_type, source_date, created_at
                FROM patient_notes
                WHERE chat_id = ? AND is_active = TRUE
                ORDER BY created_at DESC
            """, [chat_id]).fetchall()
            return [
                {
                    "content": r[0],
                    "note_type": r[1],
                    "source_date": r[2],
                    "created_at": r[3],
                }
                for r in rows
            ]
        finally:
            con.close()

    # ──────────────────────────────────────────────────────────────────────────
    # Construcción de contexto LLM
    # ──────────────────────────────────────────────────────────────────────────

    def build_llm_context(
        self,
        chat_id: int,
        context_since: Optional[datetime] = None,
    ) -> list[dict[str, str]]:
        """
        Construye el historial enriquecido para pasar al LLM en cada mensaje.

        Orden (de menor a mayor prioridad en el contexto):
          1. Notas de la paciente (alta prioridad — pueden contradecir el perfil base)
          2. Resúmenes de conversaciones anteriores (>7 días)
          3. Mensajes recientes verbatim (últimos 7 días / 40 mensajes)

        Args:
            context_since: timestamp desde el que incluir mensajes recientes.
                           Se setea cuando el usuario ejecuta /limpiar.
        """
        messages: list[dict[str, str]] = []

        # 1. Notas activas de la paciente
        notes = self.get_active_notes(chat_id)
        if notes:
            lines = []
            for n in notes:
                date_str = str(n["source_date"]) if n["source_date"] else str(n["created_at"])[:10]
                lines.append(f"- [{date_str}] {n['content']}")
            notes_block = (
                "ACTUALIZACIONES DE LA PACIENTE "
                "(estas notas tienen precedencia sobre el perfil clínico base):\n"
                + "\n".join(lines)
            )
            messages.append({"role": "user", "content": notes_block})
            messages.append({
                "role": "assistant",
                "content": (
                    "Entendido. Tomo en cuenta estas actualizaciones de la paciente "
                    "con mayor prioridad que el perfil clínico base."
                ),
            })

        # 2. Resúmenes de conversaciones anteriores
        summaries = self.get_summaries(chat_id)
        if summaries:
            parts = []
            for s in summaries:
                p_start = str(s["period_start"])[:10]
                p_end = str(s["period_end"])[:10]
                parts.append(f"[{p_start} → {p_end}]\n{s['summary']}")
            summary_block = "RESUMEN DE CONVERSACIONES ANTERIORES:\n\n" + "\n\n".join(parts)
            messages.append({"role": "user", "content": summary_block})
            messages.append({
                "role": "assistant",
                "content": "Entendido, integro el historial de conversaciones previas.",
            })

        # 3. Mensajes recientes verbatim
        recent = self.get_recent_messages(chat_id, since=context_since)
        for msg in recent:
            messages.append({"role": msg["role"], "content": msg["content"]})

        return messages


# ── Instancia global compartida por todos los handlers del bot ─────────────
conversation_store = ConversationStore()
