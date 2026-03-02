from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "db" / "solaris.db"


class RunStore(ABC):
    @abstractmethod
    def init(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_run(self, result: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> dict | None:
        raise NotImplementedError


class SQLiteRunStore(RunStore):
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
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
            conn.execute(
                """
                create table if not exists agent_steps (
                  run_id text not null,
                  step_order integer not null,
                  step text not null,
                  status text not null,
                  duration_ms real,
                  payload text,
                  primary key (run_id, step_order)
                )
                """
            )
            conn.execute(
                """
                create table if not exists evidence_packs (
                  run_id text primary key,
                  summary text,
                  confidence real,
                  payload text not null
                )
                """
            )

    def save_run(self, result: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
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

            conn.execute("delete from agent_steps where run_id = ?", (result["run_id"],))
            for idx, step in enumerate(result.get("runtime", {}).get("agent_steps", []), start=1):
                conn.execute(
                    """
                    insert into agent_steps(run_id, step_order, step, status, duration_ms, payload)
                    values(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result["run_id"],
                        idx,
                        step.get("step", "unknown"),
                        step.get("status", "ok"),
                        step.get("duration_ms", 0),
                        json.dumps(step),
                    ),
                )

            evidence = result.get("evidence_pack", {})
            conn.execute(
                """
                insert into evidence_packs(run_id, summary, confidence, payload)
                values(?, ?, ?, ?)
                on conflict(run_id) do update set
                  summary=excluded.summary,
                  confidence=excluded.confidence,
                  payload=excluded.payload
                """,
                (
                    result["run_id"],
                    evidence.get("summary"),
                    evidence.get("confidence"),
                    json.dumps(evidence),
                ),
            )

    def get_run(self, run_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("select payload from runs where run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return json.loads(row[0])


class PostgresRunStore(RunStore):
    def init(self) -> None:
        raise NotImplementedError("PostgresRunStore not wired yet. Use SQLiteRunStore for now.")

    def save_run(self, result: dict) -> None:
        raise NotImplementedError("PostgresRunStore not wired yet. Use SQLiteRunStore for now.")

    def get_run(self, run_id: str) -> dict | None:
        raise NotImplementedError("PostgresRunStore not wired yet. Use SQLiteRunStore for now.")


def get_store() -> RunStore:
    backend = os.getenv("SOLARIS_STORE", "sqlite").lower().strip()
    if backend == "postgres":
        return PostgresRunStore()
    return SQLiteRunStore()
