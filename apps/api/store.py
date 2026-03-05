from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "db" / "solaris.db"
SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


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

    @abstractmethod
    def save_location(self, loc_id: str, name: str, lat: float, lon: float, households: int, latest_run_id: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_locations(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def update_location_run(self, loc_id: str, run_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_runs_for_location(self, loc_id: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_dashboard_stats(self) -> dict:
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
            conn.execute(
                """
                create table if not exists locations (
                  loc_id text primary key,
                  name text not null,
                  lat real not null,
                  lon real not null,
                  households integer not null,
                  latest_run_id text
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

    def save_location(self, loc_id: str, name: str, lat: float, lon: float, households: int, latest_run_id: str | None = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                insert into locations(loc_id, name, lat, lon, households, latest_run_id)
                values(?, ?, ?, ?, ?, ?)
                on conflict(loc_id) do update set
                  name=excluded.name,
                  lat=excluded.lat,
                  lon=excluded.lon,
                  households=excluded.households,
                  latest_run_id=excluded.latest_run_id
                """,
                (loc_id, name, lat, lon, households, latest_run_id)
            )

    def get_locations(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("select loc_id, name, lat, lon, households, latest_run_id from locations").fetchall()
            return [dict(r) for r in rows]

    def update_location_run(self, loc_id: str, run_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("update locations set latest_run_id = ? where loc_id = ?", (run_id, loc_id))

    def get_runs_for_location(self, loc_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "select run_id, status, created_at, confidence from runs where run_id in "
                "(select latest_run_id from locations where loc_id = ?) "
                "union select r.run_id, r.status, r.created_at, r.confidence from runs r "
                "inner join locations l on r.payload like '%' || l.loc_id || '%' where l.loc_id = ? "
                "order by created_at desc limit 20",
                (loc_id, loc_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_dashboard_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            loc_count = conn.execute("select count(*) from locations").fetchone()[0]
            hh_sum = conn.execute("select coalesce(sum(households), 0) from locations").fetchone()[0]
            run_count = conn.execute("select count(*) from runs").fetchone()[0]
            avg_conf = conn.execute("select coalesce(avg(confidence), 0) from runs").fetchone()[0]
            return {
                "total_locations": loc_count,
                "total_households": hh_sum,
                "total_runs": run_count,
                "avg_confidence": round(avg_conf, 3),
            }


class PostgresRunStore(RunStore):
    def __init__(self, dsn: str):
        self.dsn = dsn
        try:
            import psycopg  # type: ignore

            self.psycopg = psycopg
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Postgres backend selected but psycopg is unavailable. Install requirements and retry."
            ) from exc

    def _connect(self):
        return self.psycopg.connect(self.dsn)

    def init(self) -> None:
        # Best effort: apply full schema if available, plus safety creation of required runtime tables.
        with self._connect() as conn:
            with conn.cursor() as cur:
                if SCHEMA_SQL_PATH.exists():
                    cur.execute(SCHEMA_SQL_PATH.read_text())

                cur.execute(
                    """
                    create table if not exists agent_steps (
                      id bigserial primary key,
                      run_id text not null,
                      agent_name text not null,
                      step_order integer not null,
                      status text not null,
                      confidence double precision,
                      assumptions jsonb,
                      quality_flags jsonb,
                      io_payload jsonb,
                      started_at timestamptz not null default now(),
                      finished_at timestamptz
                    )
                    """
                )
                cur.execute(
                    """
                    create table if not exists evidence_packs (
                      id bigserial primary key,
                      run_id text not null,
                      summary text,
                      provenance jsonb,
                      assumptions jsonb,
                      quality_flags jsonb,
                      confidence double precision,
                      payload jsonb not null,
                      created_at timestamptz not null default now()
                    )
                    """
                )
                cur.execute(
                    """
                    create table if not exists locations (
                      loc_id text primary key,
                      name text not null,
                      lat double precision not null,
                      lon double precision not null,
                      households integer not null,
                      latest_run_id text
                    )
                    """
                )
            conn.commit()

    def save_run(self, result: dict) -> None:
        quality = result["outputs"]["quality"]
        runtime = result.get("runtime", {})
        evidence = result.get("evidence_pack", {})

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into runs(run_id, status, started_at, finished_at, request_payload, output_payload, confidence_score)
                    values(%s, %s, now(), now(), %s::jsonb, %s::jsonb, %s)
                    on conflict (run_id) do update set
                      status=excluded.status,
                      finished_at=excluded.finished_at,
                      request_payload=excluded.request_payload,
                      output_payload=excluded.output_payload,
                      confidence_score=excluded.confidence_score
                    """,
                    (
                        result["run_id"],
                        quality["status"],
                        json.dumps(result.get("request", {})),
                        json.dumps(result),
                        quality["confidence"],
                    ),
                )

                cur.execute("delete from agent_steps where run_id = %s", (result["run_id"],))
                for idx, step in enumerate(runtime.get("agent_steps", []), start=1):
                    cur.execute(
                        """
                        insert into agent_steps(
                          run_id, agent_name, step_order, status, confidence, assumptions, quality_flags, io_payload, finished_at
                        )
                        values(%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, now())
                        """,
                        (
                            result["run_id"],
                            step.get("step", "unknown"),
                            idx,
                            step.get("status", "ok"),
                            step.get("confidence"),
                            json.dumps(step.get("assumptions", [])),
                            json.dumps(step.get("quality_flags", [])),
                            json.dumps(step),
                        ),
                    )

                cur.execute("delete from evidence_packs where run_id = %s", (result["run_id"],))
                cur.execute(
                    """
                    insert into evidence_packs(
                      run_id, summary, provenance, assumptions, quality_flags, confidence, payload
                    )
                    values(%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                    """,
                    (
                        result["run_id"],
                        evidence.get("summary"),
                        json.dumps(evidence.get("provenance", {})),
                        json.dumps(evidence.get("assumptions", [])),
                        json.dumps(evidence.get("quality_flags", [])),
                        evidence.get("confidence"),
                        json.dumps(evidence),
                    ),
                )
            conn.commit()

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select output_payload from runs where run_id = %s", (run_id,))
                row = cur.fetchone()
        if not row:
            return None

        payload = row[0]
        if isinstance(payload, str):
            return json.loads(payload)
        return payload

    def save_location(self, loc_id: str, name: str, lat: float, lon: float, households: int, latest_run_id: str | None = None) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into locations(loc_id, name, lat, lon, households, latest_run_id)
                    values(%s, %s, %s, %s, %s, %s)
                    on conflict (loc_id) do update set
                      name=excluded.name,
                      lat=excluded.lat,
                      lon=excluded.lon,
                      households=excluded.households,
                      latest_run_id=excluded.latest_run_id
                    """,
                    (loc_id, name, lat, lon, households, latest_run_id)
                )
            conn.commit()

    def get_locations(self) -> list[dict]:
        from psycopg.rows import dict_row # type: ignore
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("select loc_id, name, lat, lon, households, latest_run_id from locations")
                return cur.fetchall()

    def update_location_run(self, loc_id: str, run_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("update locations set latest_run_id = %s where loc_id = %s", (run_id, loc_id))
            conn.commit()

    def get_runs_for_location(self, loc_id: str) -> list[dict]:
        from psycopg.rows import dict_row  # type: ignore
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "select run_id, status, started_at as created_at, confidence_score as confidence "
                    "from runs where run_id in (select latest_run_id from locations where loc_id = %s) "
                    "order by started_at desc limit 20",
                    (loc_id,),
                )
                return cur.fetchall()

    def get_dashboard_stats(self) -> dict:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select count(*) from locations")
                loc_count = cur.fetchone()[0]
                cur.execute("select coalesce(sum(households), 0) from locations")
                hh_sum = cur.fetchone()[0]
                cur.execute("select count(*) from runs")
                run_count = cur.fetchone()[0]
                cur.execute("select coalesce(avg(confidence_score), 0) from runs")
                avg_conf = cur.fetchone()[0]
                return {
                    "total_locations": loc_count,
                    "total_households": int(hh_sum),
                    "total_runs": run_count,
                    "avg_confidence": round(float(avg_conf), 3),
                }


def get_store() -> RunStore:
    backend = os.getenv("SOLARIS_STORE", "sqlite").lower().strip()
    if backend == "postgres":
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("SOLARIS_STORE=postgres requires DATABASE_URL")
        return PostgresRunStore(dsn)
    return SQLiteRunStore()
