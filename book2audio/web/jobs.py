"""The job registry on SQLite.

There is one user and one job, so a broker and a separate worker are not needed.
A table with the status is enough: the web process can be restarted without
losing state, and the background thread reads the same database.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path


class State(str, Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    READY = "ready_for_review"
    QUEUED = "queued"
    SYNTHESIZING = "synthesizing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATES = {State.EXTRACTING, State.QUEUED, State.SYNTHESIZING}
FINAL_STATES = {State.DONE, State.FAILED, State.CANCELLED}

# There is no way back out of these states. FAILED is not among them: a failure
# during assembly must not cost the whole reading again, and the cache makes a
# retry nearly free.
IRREVERSIBLE_STATES = {State.DONE, State.CANCELLED}


@dataclass
class Job:
    id: str
    source: Path | str
    language: str
    gender: str
    state: State = State.UPLOADED
    voice: str | None = None
    selection: str | None = None
    # The folder for this book. Empty means the folder set when the server started.
    destination: str | None = None
    audio_format: str = "m4b"
    stage: str = ""
    done: int = 0
    total: int = 0
    error: str = ""
    result: Path | None = None
    title: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if isinstance(self.source, str):
            self.source = Path(self.source)
        if isinstance(self.result, str) and self.result:
            self.result = Path(self.result)

    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state.value,
            "language": self.language,
            "gender": self.gender,
            "voice": self.voice,
            "format": self.audio_format,
            "stage": self.stage,
            "done": self.done,
            "total": self.total,
            "error": self.error,
            "title": self.title,
            "result": self.result.name if self.result else None,
            "created_at": self.created_at,
        }


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    language TEXT NOT NULL,
    gender TEXT NOT NULL,
    state TEXT NOT NULL,
    voice TEXT,
    selection TEXT,
    audio_format TEXT NOT NULL DEFAULT 'm4b',
    stage TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    result TEXT,
    title TEXT NOT NULL DEFAULT '',
    review TEXT,
    created_at TEXT NOT NULL
);
"""

# Columns added after the first release. The user already has the database with
# finished books in it, so it cannot be recreated.
ADDED_COLUMNS = {"destination": "TEXT"}


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            self._migrate(db)

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        """Adds the columns an existing database does not have yet."""
        present = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        for column, kind in ADDED_COLUMNS.items():
            if column not in present:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {kind}")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def create(self, source: Path, language: str, gender: str, **extra) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12], source=source, language=language, gender=gender, **extra
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO jobs (id, source, language, gender, state, voice, "
                "selection, audio_format, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    job.id,
                    str(job.source),
                    job.language,
                    job.gender,
                    job.state.value,
                    job.voice,
                    job.selection,
                    job.audio_format,
                    job.created_at,
                ),
            )
        return job

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            source=row["source"],
            language=row["language"],
            gender=row["gender"],
            state=State(row["state"]),
            voice=row["voice"],
            selection=row["selection"],
            destination=row["destination"],
            audio_format=row["audio_format"],
            stage=row["stage"],
            done=row["done"],
            total=row["total"],
            error=row["error"],
            result=Path(row["result"]) if row["result"] else None,
            title=row["title"],
            created_at=row["created_at"],
        )

    def get(self, job_id: str) -> Job | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def recent(self, limit: int = 50) -> list[Job]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def _require(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        return job

    def set_state(self, job_id: str, state: State) -> None:
        """A done or cancelled job cannot move back, a failed one can."""
        current = self._require(job_id)
        if current.state in IRREVERSIBLE_STATES and state not in FINAL_STATES:
            raise ValueError(f"cannot move the job from {current.state.value} to {state.value}")
        with self._connect() as db:
            # The old error stops meaning anything once the job leaves FAILED.
            db.execute("UPDATE jobs SET state = ?, error = '' WHERE id = ?", (state.value, job_id))

    def mark_queued(self, job_id: str) -> None:
        self.set_state(job_id, State.QUEUED)

    def set_progress(self, job_id: str, stage: str, done: int, total: int) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET stage = ?, done = ?, total = ? WHERE id = ?",
                (stage, done, total, job_id),
            )

    def set_title(self, job_id: str, title: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE jobs SET title = ? WHERE id = ?", (title, job_id))

    def fail(self, job_id: str, message: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET state = ?, error = ? WHERE id = ?",
                (State.FAILED.value, message, job_id),
            )

    def finish(self, job_id: str, result: Path) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET state = ?, result = ? WHERE id = ?",
                (State.DONE.value, str(result), job_id),
            )

    def cancel(self, job_id: str) -> None:
        """Only an unfinished job can be cancelled."""
        current = self._require(job_id)
        if current.state in FINAL_STATES:
            raise ValueError(
                f"cannot move the job from {current.state.value} to {State.CANCELLED.value}"
            )
        with self._connect() as db:
            db.execute("UPDATE jobs SET state = ? WHERE id = ?", (State.CANCELLED.value, job_id))

    def is_cancelled(self, job_id: str) -> bool:
        job = self.get(job_id)
        return job is not None and job.state == State.CANCELLED

    def next_queued(self) -> Job | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE state = ? ORDER BY created_at, rowid LIMIT 1",
                (State.QUEUED.value,),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def save_review(self, job_id: str, chapters: list[dict]) -> None:
        """The text after the preview edits. It survives a process restart."""
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET review = ? WHERE id = ?",
                (json.dumps(chapters, ensure_ascii=False), job_id),
            )

    def get_review(self, job_id: str) -> list[dict] | None:
        with self._connect() as db:
            row = db.execute("SELECT review FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return json.loads(row["review"]) if row and row["review"] else None

    def set_options(
        self,
        job_id: str,
        voice: str,
        selection: str,
        audio_format: str,
        destination: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET voice = ?, selection = ?, audio_format = ?, "
                "destination = ? WHERE id = ?",
                (voice, selection, audio_format, destination, job_id),
            )
