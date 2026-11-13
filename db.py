import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import os
DB_PATH = os.getenv("DB_PATH", "interviews.db")


@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                job_description TEXT NOT NULL,
                questions TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answers (
                session_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                answer TEXT NOT NULL,
                evaluation TEXT NOT NULL,
                overall_score REAL NOT NULL,
                PRIMARY KEY (session_id, question_index)
            )
            """
        )


def create_session(session_id: str, job_description: str, questions: list) -> None:
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (id, job_description, questions, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                session_id,
                job_description,
                json.dumps(questions),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def get_session(session_id: str):
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return {
        "job_description": row["job_description"],
        "questions": json.loads(row["questions"]),
    }


def save_answer(session_id: str, question_index: int, answer: str, evaluation: dict) -> None:
    with db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO answers "
            "(session_id, question_index, answer, evaluation, overall_score) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                question_index,
                answer,
                json.dumps(evaluation),
                evaluation["overall_score"],
            ),
        )


def get_answers(session_id: str) -> dict:
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM answers WHERE session_id = ? ORDER BY question_index",
            (session_id,),
        ).fetchall()
    return {
        row["question_index"]: {
            "answer": row["answer"],
            "evaluation": json.loads(row["evaluation"]),
        }
        for row in rows
    }
def list_sessions() -> list:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id,
                   s.created_at,
                   COUNT(a.question_index) AS answered,
                   AVG(a.overall_score) AS average_score
            FROM sessions s
            LEFT JOIN answers a ON a.session_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "answered": row["answered"],
            "average_score": (
                round(row["average_score"], 1)
                if row["average_score"] is not None
                else None
            ),
        }
        for row in rows
    ]