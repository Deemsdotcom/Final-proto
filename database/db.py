"""Database connection and CRUD helpers.

All functions use short-lived connections with a small retry loop for
SQLite-locked errors. Schema is created on first call to init_db().
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

DB_PATH = Path(__file__).parent.parent / "recruitment.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _get_recruiter_password() -> str:
    """Read recruiter password from Streamlit secrets, then env, then fallback.

    Streamlit secrets are checked first so production deployments use the
    configured password. Falls back to the env var, then a local-dev default
    so the app still runs without any config (with a weak password).
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "RECRUITER_PASSWORD" in st.secrets:
            return str(st.secrets["RECRUITER_PASSWORD"])
    except Exception:
        pass
    return os.getenv("RECRUITER_PASSWORD", "changeme-local-dev")


DEFAULT_RECRUITER_USERNAME = "recruiter"
DEFAULT_RECRUITER_PASSWORD = _get_recruiter_password()


def _hash_password(password: str) -> str:
    """SHA-256 hash. Fine for a pilot; swap for bcrypt in production."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Short-lived connection with retry on 'database is locked'."""
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
                return
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower() and attempt < 2:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _migrate_final_scores(conn: sqlite3.Connection) -> None:
    """Add new columns to final_scores if missing.

    Idempotent: safe to run on a fresh DB or one already migrated. We don't
    DROP the old proactivity / learning_mindset columns because SQLite's
    ALTER TABLE DROP COLUMN is only available on 3.35+; instead we just
    stop writing to them. They'll sit at NULL for new rows.

    Each ALTER is wrapped in try/except: SQLite's ADD COLUMN with NOT NULL
    can fail unpredictably on populated tables across versions, and we
    don't want a single column add taking down app startup. If a column
    add fails the app still boots and writes to the missing column just
    silently no-op.
    """
    cols = _existing_columns(conn, "final_scores")
    additions = [
        ("competency_l3_growth_mindset", "REAL"),
        ("ai_flag_logical",   "INTEGER NOT NULL DEFAULT 0"),
        ("ai_flag_numerical", "INTEGER NOT NULL DEFAULT 0"),
        ("ai_flag_verbal",    "INTEGER NOT NULL DEFAULT 0"),
        ("ai_flag_layer2",    "INTEGER NOT NULL DEFAULT 0"),
    ]
    for name, decl in additions:
        if name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE final_scores ADD COLUMN {name} {decl}")
        except sqlite3.OperationalError as e:
            # Common cause: NOT NULL DEFAULT on a populated table in some
            # SQLite versions, or a phantom column the PRAGMA didn't see.
            # Either way we keep going so the app boots.
            import sys
            print(
                f"[migrate] skipped ALTER final_scores ADD COLUMN {name}: {e}",
                file=sys.stderr,
            )


def _migrate_layer3_results(conn: sqlite3.Connection) -> None:
    """Add new columns to layer3_results if missing.

    v8.1 adds time-to-record tracking: how many seconds elapsed between
    the AI finishing the question and the candidate clicking record. Long
    pauses are flagged in the recruiter dashboard as a possible AI signal.

    Same defensive try/except as _migrate_final_scores: don't take the
    app down if one ALTER fails on a populated production DB.
    """
    cols = _existing_columns(conn, "layer3_results")
    additions = [
        ("main_time_to_record_seconds", "REAL"),
        ("followup_time_to_record_seconds", "REAL"),
        ("typed_fallback_used", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for name, decl in additions:
        if name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE layer3_results ADD COLUMN {name} {decl}")
        except sqlite3.OperationalError as e:
            import sys
            print(
                f"[migrate] skipped ALTER layer3_results ADD COLUMN {name}: {e}",
                file=sys.stderr,
            )


def init_db() -> bool:
    """Initialize schema and seed/sync default recruiter.

    Always syncs the recruiter password to whatever's in secrets/env on
    startup, so rotating the secret immediately takes effect. Returns True
    if the recruiter row was freshly created (not just synced).
    """
    freshly_seeded = False
    with get_conn() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        # Migrate older DBs to add v7 columns if they don't exist yet.
        _migrate_final_scores(conn)
        _migrate_layer3_results(conn)

        current_hash = _hash_password(DEFAULT_RECRUITER_PASSWORD)
        cur = conn.execute(
            "SELECT password_hash FROM recruiter_auth WHERE username = ?",
            (DEFAULT_RECRUITER_USERNAME,),
        )
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO recruiter_auth (username, password_hash) VALUES (?, ?)",
                (DEFAULT_RECRUITER_USERNAME, current_hash),
            )
            freshly_seeded = True
        elif row["password_hash"] != current_hash:
            conn.execute(
                "UPDATE recruiter_auth SET password_hash = ? WHERE username = ?",
                (current_hash, DEFAULT_RECRUITER_USERNAME),
            )
    return freshly_seeded


# ----- Candidates -----

def create_candidate(candidate_id: str, full_name: str, email: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO candidates (candidate_id, full_name, email, started_at, current_stage)
               VALUES (?, ?, ?, ?, 'intro')""",
            (candidate_id, full_name, email, datetime.utcnow().isoformat()),
        )


def get_candidate(candidate_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None


def find_candidate_by_email(email: str) -> Optional[dict]:
    """Used for resume flow: find the most recent incomplete candidate for this email."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM candidates
               WHERE email = ? AND completed_at IS NULL
               ORDER BY started_at DESC LIMIT 1""",
            (email,),
        ).fetchone()
        return dict(row) if row else None


def set_stage(candidate_id: str, stage: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE candidates SET current_stage = ? WHERE candidate_id = ?",
            (stage, candidate_id),
        )


def mark_complete(candidate_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE candidates
               SET completed_at = ?, current_stage = 'done'
               WHERE candidate_id = ?""",
            (datetime.utcnow().isoformat(), candidate_id),
        )


# ----- Layer 1 -----

def save_layer1_result(
    candidate_id: str,
    theme: str,
    question_id: str,
    question_text: str,
    options_shown: list,
    correct_option: str,
    candidate_answer: Optional[str],
    is_correct: bool,
    time_taken_seconds: int,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO layer1_results
               (candidate_id, theme, question_id, question_text, options_shown,
                correct_option, candidate_answer, is_correct, time_taken_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id, theme, question_id, question_text,
                json.dumps(options_shown), correct_option, candidate_answer,
                1 if is_correct else 0, time_taken_seconds,
            ),
        )


def get_layer1_results(candidate_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM layer1_results WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_layer1_answered(candidate_id: str, theme: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM layer1_results WHERE candidate_id = ? AND theme = ?",
            (candidate_id, theme),
        ).fetchone()
        return row["c"]


# ----- Layer 2 -----

def save_layer2_simulation(
    candidate_id: str,
    final_state: dict,
    weekly_log: list,
    weeks_played: int,
    final_cash: float,
    final_reputation: float,
    projects_completed: int,
    projects_cancelled: int,
    tradeoff_choice: Optional[str],
    outcome_score: float,
    process_score: float,
    layer2_total: float,
    time_taken_seconds: int,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO layer2_simulation
               (candidate_id, final_state_json, weekly_log_json, weeks_played,
                final_cash, final_reputation, projects_completed, projects_cancelled,
                tradeoff_choice, outcome_score, process_score, layer2_total,
                time_taken_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id, json.dumps(final_state), json.dumps(weekly_log),
                weeks_played, final_cash, final_reputation,
                projects_completed, projects_cancelled, tradeoff_choice,
                outcome_score, process_score, layer2_total,
                time_taken_seconds,
            ),
        )


def get_layer2_simulation(candidate_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM layer2_simulation WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None


def has_layer2_simulation(candidate_id: str) -> bool:
    return get_layer2_simulation(candidate_id) is not None


# ----- Layer 3 -----

def save_layer3_result(
    candidate_id: str,
    competency_order: int,
    competency_id: str,
    competency_key: str,
    competency_name: str,
    main_question: str,
    main_transcript: str,
    main_audio_duration_seconds: float,
    followup_bucket: str | None,
    followup_question: str | None,
    followup_transcript: str | None,
    followup_audio_duration_seconds: float | None,
    competency_score: int,
    scripted_flag: bool,
    rationale: str,
    main_time_to_record_seconds: float | None = None,
    followup_time_to_record_seconds: float | None = None,
    typed_fallback_used: bool = False,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO layer3_results
               (candidate_id, competency_order, competency_id, competency_key,
                competency_name, main_question, main_transcript,
                main_audio_duration_seconds, followup_bucket, followup_question,
                followup_transcript, followup_audio_duration_seconds,
                competency_score, scripted_flag, rationale,
                main_time_to_record_seconds, followup_time_to_record_seconds,
                typed_fallback_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id, competency_order, competency_id, competency_key,
                competency_name, main_question, main_transcript,
                main_audio_duration_seconds, followup_bucket, followup_question,
                followup_transcript, followup_audio_duration_seconds,
                competency_score, 1 if scripted_flag else 0, rationale,
                main_time_to_record_seconds, followup_time_to_record_seconds,
                1 if typed_fallback_used else 0,
            ),
        )


def get_layer3_results(candidate_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM layer3_results WHERE candidate_id = ? ORDER BY competency_order",
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_layer3_answered(candidate_id: str) -> int:
    """Number of competencies fully scored so far (0..5)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM layer3_results "
            "WHERE candidate_id = ? AND competency_score IS NOT NULL",
            (candidate_id,),
        ).fetchone()
        return row["c"]


def count_layer3_typed_fallback(candidate_id: str) -> int:
    """How many L3 competencies the candidate completed using the typed-fallback escape.

    Used by the recruiter dashboard to show a top-level flag without
    having to scan each transcript row.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM layer3_results "
            "WHERE candidate_id = ? AND typed_fallback_used = 1",
            (candidate_id,),
        ).fetchone()
        return row["c"]


# ----- Final scores -----

def save_final_score(data: dict) -> None:
    """Write a row into final_scores. Defensive against schema drift.

    Only columns that actually exist in final_scores right now are
    included in the INSERT. If a column add migration failed on this
    DB (the in-place ALTER TABLE is wrapped in try/except so the app
    boots even if one ALTER fails), the corresponding key in `data`
    is just dropped silently. ai_flag_* and layer3_skipped default
    to 0 when the caller didn't supply them; everything else defaults
    to None.
    """
    desired_cols = [
        "candidate_id", "layer1_score", "layer2_score", "layer3_score",
        "overall_score", "competency_analytical", "competency_numerical",
        "competency_verbal", "competency_strategic", "competency_adaptability",
        "competency_l3_growth_mindset",
        "competency_l3_adaptability", "competency_l3_collaboration",
        "competency_l3_self_reflection",
        "ai_flag_logical", "ai_flag_numerical", "ai_flag_verbal", "ai_flag_layer2",
        "top_fit", "recruiter_summary", "candidate_feedback",
        "layer3_skipped", "layer3_skip_reason",
    ]
    with get_conn() as conn:
        fs_cols = _existing_columns(conn, "final_scores")
        cols = [c for c in desired_cols if c in fs_cols]
        if not cols:
            return
        placeholders = ",".join(["?"] * len(cols))

        def _default_for(col: str):
            if col.startswith("ai_flag_") or col == "layer3_skipped":
                return 0
            return None

        conn.execute(
            f"INSERT OR REPLACE INTO final_scores ({','.join(cols)}) VALUES ({placeholders})",
            tuple(data.get(c, _default_for(c)) for c in cols),
        )


def get_final_score(candidate_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM final_scores WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_completed_candidates() -> list[dict]:
    """Join candidates + final_scores for the recruiter dashboard.

    Defensive against schema drift: only SELECT columns that actually
    exist in final_scores right now. If a migration for a column failed
    on this DB (the in-place ALTER TABLE is wrapped in try/except so app
    boot can't be blocked by a single column add), the column is simply
    omitted from the result dicts. The dashboard code uses .get() on
    every read so missing keys degrade gracefully.
    """
    with get_conn() as conn:
        fs_cols = _existing_columns(conn, "final_scores")
        cand_cols = ["candidate_id", "full_name", "email", "started_at", "completed_at"]
        # Optional final_scores columns the dashboard reads, in priority order.
        optional = [
            "layer1_score", "layer2_score", "layer3_score", "overall_score",
            "competency_analytical", "competency_numerical", "competency_verbal",
            "competency_strategic", "competency_adaptability",
            "competency_l3_growth_mindset",
            "competency_l3_adaptability", "competency_l3_collaboration",
            "competency_l3_self_reflection",
            "ai_flag_logical", "ai_flag_numerical", "ai_flag_verbal", "ai_flag_layer2",
            "top_fit", "recruiter_summary", "candidate_feedback",
            "layer3_skipped", "layer3_skip_reason",
            # Legacy / pre-merge columns - keep so old rows still render.
            "competency_l3_proactivity", "competency_l3_learning_mindset",
            "competency_l3_growth_driven_mindset",
        ]
        present = [c for c in optional if c in fs_cols]

        select_parts = [f"c.{c}" for c in cand_cols] + [f"f.{c}" for c in present]
        sql = (
            "SELECT " + ", ".join(select_parts) + " "
            "FROM candidates c "
            "JOIN final_scores f ON c.candidate_id = f.candidate_id "
            "WHERE c.completed_at IS NOT NULL "
            "ORDER BY c.completed_at DESC"
        )
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


# ----- Auth -----

def verify_recruiter(username: str, password: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM recruiter_auth WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False
        return row["password_hash"] == _hash_password(password)


def purge_expired_candidates(ttl_seconds: int = 7200) -> int:
    """Hard-delete incomplete candidate attempts older than ttl_seconds.

    Cascades across all the per-candidate tables: layer1_results,
    layer2_simulation, layer3_results, final_scores, and finally the
    candidates row itself. The candidate's email and name go with the
    candidates row, so re-using the same email after the TTL expires
    starts a fresh assessment from scratch.

    completed_at IS NULL is the safety net: completed assessments persist
    indefinitely for the recruiter dashboard. Only abandoned/in-progress
    attempts get purged.

    Returns the number of candidates purged. Idempotent.
    """
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(seconds=ttl_seconds)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT candidate_id FROM candidates "
            "WHERE started_at < ? AND completed_at IS NULL",
            (cutoff,),
        ).fetchall()
        if not rows:
            return 0
        ids = [r["candidate_id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        # Wipe per-candidate rows from every table that references them.
        # candidates row goes LAST because the FK references it.
        for table in (
            "layer1_results",
            "layer2_simulation",
            "layer3_results",
            "final_scores",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE candidate_id IN ({placeholders})",
                ids,
            )
        conn.execute(
            f"DELETE FROM candidates WHERE candidate_id IN ({placeholders})",
            ids,
        )
        return len(ids)


def clear_layer3_results(candidate_id: str) -> None:
    """Wipe any previously-saved Layer 3 rows for a candidate.

    Called at the start of a fresh interview so re-takes don't leave
    duplicate competency rows behind (layer3_results has no UNIQUE
    constraint on (candidate_id, competency_id)).
    """
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM layer3_results WHERE candidate_id = ?",
            (candidate_id,),
        )


def clear_layer1_results(candidate_id: str) -> None:
    """Wipe Layer 1 answer rows for a candidate (used on coarse resume)."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM layer1_results WHERE candidate_id = ?",
            (candidate_id,),
        )


def clear_layer2_simulation(candidate_id: str) -> None:
    """Wipe the Layer 2 simulation row for a candidate (used on coarse resume)."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM layer2_simulation WHERE candidate_id = ?",
            (candidate_id,),
        )
