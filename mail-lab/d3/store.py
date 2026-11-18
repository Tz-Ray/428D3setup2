import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from .plan import Plan


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def database(path):
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        with db:
            yield db


def initialize(path):
    with database(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS plan (
                id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, content TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checks (
                id TEXT PRIMARY KEY, started TEXT NOT NULL, status TEXT NOT NULL, record TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sequence_controls (
                id TEXT PRIMARY KEY, state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS draft_mail (
                id INTEGER PRIMARY KEY, check_id TEXT NOT NULL REFERENCES checks(id),
                stage TEXT NOT NULL, delivered_at TEXT NOT NULL, sender TEXT NOT NULL,
                recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, media_type TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS draft_mail_by_check ON draft_mail(check_id, id);
            CREATE UNIQUE INDEX IF NOT EXISTS single_active_check ON checks(status)
                WHERE status='running';
        """)
        db.execute("INSERT OR IGNORE INTO plan VALUES (1, 0, ?)", (Plan().model_dump_json(),))
        for row in db.execute(
            "SELECT record FROM checks WHERE status IN ('queued','running','waiting_for_controls')"
        ).fetchall():
            record = json.loads(row["record"])
            for slot in record.get("controls", []):
                if slot["status"] == "running":
                    slot["status"] = "unverified"
            reason = "The sandbox stopped before this variation started." if record["status"] == "queued" else "The sandbox stopped during this check."
            record.update(status="interrupted", error=reason, ended=now())
            update_check(db, record)


def read_plan(db):
    row = db.execute("SELECT revision, content FROM plan WHERE id=1").fetchone()
    # Populate new fields on read. Older operator notes stay in their original field.
    plan = Plan.model_validate_json(row["content"]).model_dump()
    return {"revision": row["revision"], "plan": plan}


def update_check(db, record):
    db.execute("UPDATE checks SET status=?, record=? WHERE id=?",
               (record["status"], json.dumps(record), record["id"]))


def insert_check(db, record):
    db.execute("INSERT INTO checks VALUES(?,?,?,?)",
               (record["id"], record["started"], record["status"], json.dumps(record)))
