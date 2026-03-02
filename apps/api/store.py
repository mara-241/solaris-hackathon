from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "db" / "solaris.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            create table if not exists runs (
              run_id text primary key,
              status text not null,
              created_at text not null,
              confidence real,
              payload text not null
            )
            """
        )


def save_run(result: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into runs(run_id, status, created_at, confidence, payload)
            values(?, ?, ?, ?, ?)
            on conflict(run_id) do update set
              status=excluded.status,
              created_at=excluded.created_at,
              confidence=excluded.confidence,
              payload=excluded.payload
            """,
            (
                result["run_id"],
                result["outputs"]["quality"]["status"],
                result["created_at"],
                result["outputs"]["quality"]["confidence"],
                json.dumps(result),
            ),
        )


def get_run(run_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("select payload from runs where run_id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return json.loads(row[0])
