"""Load and save conversations (sessions) in Postgres."""

from psycopg.types.json import Jsonb

from db import pool
from models import Session


def load_session(session_id: str) -> Session | None:
    """The saved conversation with this ID, or None if there isn't one."""
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id, verified, customer_id, failed_attempts, actions_taken, escalation_id, messages
            FROM sessions
            WHERE id = %s
            """,
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return Session(**row)


def save_session(session: Session) -> None:
    """Insert the conversation the first time, update it every time after."""
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, verified, customer_id, failed_attempts, actions_taken, escalation_id, messages)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                verified        = EXCLUDED.verified,
                customer_id     = EXCLUDED.customer_id,
                failed_attempts = EXCLUDED.failed_attempts,
                actions_taken   = EXCLUDED.actions_taken,
                escalation_id   = EXCLUDED.escalation_id,
                messages        = EXCLUDED.messages,
                updated_at      = now()
            """,
            (session.id, session.verified, session.customer_id, session.failed_attempts,
             list(session.actions_taken), session.escalation_id, Jsonb(session.messages)),
        )