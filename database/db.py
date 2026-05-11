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

import bcrypt

DB_PATH = Path(__file__).parent.parent / "recruitment.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_recruiter_password() -> str:
    """Read recruiter password from Streamlit secrets, then env, then fallback.

    Streamlit secrets are checked first so production deployments use the
    configured password. Falls back to the env var, then a local-dev default
    so the app still runs without any config (with a weak password).

    Always call this at the point of use, not at module import time. On
    Streamlit Cloud, st.secrets is not always populated when this module
    is first imported; caching the result at import would silently fall
    back to the local-dev default.
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "RECRUITER_PASSWORD" in st.secrets:
            return str(st.secrets["RECRUITER_PASSWORD"])
    except Exception:
        pass
    return os.getenv("RECRUITER_PASSWORD", "changeme-local-dev")


# Backwards-compatible private alias. Prefer the public name above.
_get_recruiter_password = get_recruiter_password


DEFAULT_RECRUITER_USERNAME = "recruiter"


def _hash_password(password: str) -> str:
    """Hash a password using bcrypt with a per-call salt.

    Returns the standard `$2b$...` modular crypt format. Non-deterministic:
    two calls with the same input produce different hashes (which is the
    point — bcrypt embeds the salt in the output).
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _legacy_sha256(password: str) -> str:
    """Legacy SHA-256 hex digest used by the previous version of this app.

    Kept only so we can recognize and seamlessly upgrade pre-existing
    recruiter rows that were seeded under the old scheme.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(password: str, stored_hash: str) -> bool:
    """Check a candidate password against a stored hash.

    Recognizes both the new bcrypt format (`$2...`) and the legacy SHA-256
    hex format. Callers that need to migrate the stored hash should call
    `_hash_password` after a successful legacy match and persist the new
    value.
    """
    if not stored_hash:
        return False
    if stored_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii"))
        except (ValueError, TypeError):
            return False
    # Legacy SHA-256 hex digest path.
    return stored_hash == _legacy_sha256(password)


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


def init_db() -> bool:
    """Initialize schema and seed/sync default recruiter.

    Always syncs the recruiter password to whatever's in secrets/env on
    startup, so rotating the secret immediately takes effect. Returns True
    if the recruiter row was freshly created (not just synced).
    """
    freshly_seeded = False
    configured_password = _get_recruiter_password()
    with get_conn() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        # Race-safe seed: INSERT OR IGNORE silently no-ops if another
        # concurrent init_db() (different Streamlit session, same SQLite
        # file) already inserted the row. cur.rowcount is 1 on success,
        # 0 if the row already existed.
        cur = conn.execute(
            "INSERT OR IGNORE INTO recruiter_auth (username, password_hash) VALUES (?, ?)",
            (DEFAULT_RECRUITER_USERNAME, _hash_password(configured_password)),
        )
        freshly_seeded = cur.rowcount > 0

        if not freshly_seeded:
            # Row already existed — check for secret rotation.
            row = conn.execute(
                "SELECT password_hash FROM recruiter_auth WHERE username = ?",
                (DEFAULT_RECRUITER_USERNAME,),
            ).fetchone()
            if row:
                # bcrypt hashes are non-deterministic, so we can't compare
                # hashes directly to detect a secret rotation. Instead we
                # verify the currently-configured password against the
                # stored hash; mismatch → re-hash, legacy SHA-256 → upgrade.
                stored = row["password_hash"]
                currently_valid = _verify_password(configured_password, stored)
                is_legacy = bool(stored) and not stored.startswith("$2")
                if not currently_valid or is_legacy:
                    conn.execute(
                        "UPDATE recruiter_auth SET password_hash = ? WHERE username = ?",
                        (_hash_password(configured_password), DEFAULT_RECRUITER_USERNAME),
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
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO layer3_results
               (candidate_id, competency_order, competency_id, competency_key,
                competency_name, main_question, main_transcript,
                main_audio_duration_seconds, followup_bucket, followup_question,
                followup_transcript, followup_audio_duration_seconds,
                competency_score, scripted_flag, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id, competency_order, competency_id, competency_key,
                competency_name, main_question, main_transcript,
                main_audio_duration_seconds, followup_bucket, followup_question,
                followup_transcript, followup_audio_duration_seconds,
                competency_score, 1 if scripted_flag else 0, rationale,
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


def clear_layer3_results(candidate_id: str) -> None:
    """Wipe any previously-saved Layer 3 rows for a candidate.

    Called at the start of a fresh interview so re-takes don't leave
    duplicate competency rows behind (layer3_results has no UNIQUE
    constraint on (candidate_id, competency_id), so without this a
    re-take would silently double-write).
    """
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM layer3_results WHERE candidate_id = ?",
            (candidate_id,),
        )


# ----- Final scores -----

def save_final_score(data: dict) -> None:
    """data must contain every column in final_scores."""
    cols = [
        "candidate_id", "layer1_score", "layer2_score", "layer3_score",
        "overall_score", "competency_analytical", "competency_numerical",
        "competency_verbal", "competency_strategic", "competency_adaptability",
        "competency_l3_proactivity", "competency_l3_learning_mindset",
        "competency_l3_adaptability", "competency_l3_collaboration",
        "competency_l3_self_reflection",
        "top_fit", "recruiter_summary", "candidate_feedback",
    ]
    placeholders = ",".join(["?"] * len(cols))
    with get_conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO final_scores ({','.join(cols)}) VALUES ({placeholders})",
            tuple(data[c] for c in cols),
        )


def get_final_score(candidate_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM final_scores WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_completed_candidates() -> list[dict]:
    """Join candidates + final_scores for the recruiter dashboard."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.candidate_id, c.full_name, c.email, c.started_at, c.completed_at,
                      f.layer1_score, f.layer2_score, f.layer3_score, f.overall_score,
                      f.competency_analytical, f.competency_numerical, f.competency_verbal,
                      f.competency_strategic, f.competency_adaptability,
                      f.competency_l3_proactivity, f.competency_l3_learning_mindset,
                      f.competency_l3_adaptability, f.competency_l3_collaboration,
                      f.competency_l3_self_reflection,
                      f.top_fit, f.recruiter_summary, f.candidate_feedback
               FROM candidates c
               JOIN final_scores f ON c.candidate_id = f.candidate_id
               WHERE c.completed_at IS NOT NULL
               ORDER BY c.completed_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


# ----- Auth -----

def verify_recruiter(username: str, password: str) -> bool:
    """Check the recruiter username/password.

    Accepts both bcrypt-hashed and legacy SHA-256-hashed rows. If a legacy
    row matches, it is transparently upgraded to a fresh bcrypt hash so the
    next login uses the stronger scheme.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM recruiter_auth WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False
        stored = row["password_hash"]
        if not _verify_password(password, stored):
            return False
        # Successful login — opportunistically upgrade legacy SHA-256 rows.
        if stored and not stored.startswith("$2"):
            conn.execute(
                "UPDATE recruiter_auth SET password_hash = ? WHERE username = ?",
                (_hash_password(password), username),
            )
        return True
