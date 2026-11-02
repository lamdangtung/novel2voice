"""Durable chapter queue and schedules, independent of Telegram networking."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class BotStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY, profile TEXT NOT NULL, chapter INTEGER NOT NULL,
                    settings TEXT NOT NULL, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                    run_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                    progress TEXT NOT NULL DEFAULT '{}', result TEXT, error TEXT,
                    started_at REAL, finished_at REAL, message_id INTEGER,
                    notify INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS active_chapter ON jobs(profile, chapter)
                    WHERE status IN ('queued','running','succeeded');
                CREATE TABLE IF NOT EXISTS receipts(update_id INTEGER PRIMARY KEY, reply TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def offset(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='offset'").fetchone()
            return int(row[0]) if row else 0

    def set_offset(self, offset):
        with self.db() as db:
            db.execute("INSERT INTO settings VALUES ('offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(offset),))

    def receipt(self, update_id, reply=None):
        with self.db() as db:
            if reply is not None:
                db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?)', (update_id, reply))
            row = db.execute('SELECT reply FROM receipts WHERE update_id=?', (update_id,)).fetchone()
            return row[0] if row else None

    def enqueue(self, profile, chapter, settings, user_id, chat_id, run_at):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute("SELECT * FROM jobs WHERE profile=? AND chapter=? AND status IN ('queued','running','succeeded')",
                                  (profile, chapter)).fetchone()
            if existing:
                return dict(existing), False
            cursor = db.execute('''INSERT INTO jobs(profile,chapter,settings,user_id,chat_id,run_at,updated_at)
                VALUES (?,?,?,?,?,?,?)''', (profile, chapter, json.dumps(settings), user_id, chat_id, run_at, time.time()))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (cursor.lastrowid,)).fetchone()), True

    def get(self, job_id, user_id=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?' + (' AND user_id=?' if user_id is not None else ''),
                             (job_id, user_id) if user_id is not None else (job_id,)).fetchone()
            return dict(row) if row else None

    def list(self, user_id):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT 10', (user_id,))]

    def claim(self, now=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' AND run_at<=? ORDER BY run_at,id LIMIT 1",
                             (time.time() if now is None else now,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running',started_at=?,updated_at=?,notify=1 WHERE id=?",
                       (time.time(), time.time(), row['id']))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())

    def progress(self, job_id, payload, notify=False):
        with self.db() as db:
            db.execute('UPDATE jobs SET progress=?,notify=MAX(notify,?),updated_at=? WHERE id=?',
                       (json.dumps(payload), int(notify), time.time(), job_id))

    def finish(self, job_id, status, result=None, error=None):
        with self.db() as db:
            db.execute('UPDATE jobs SET status=?,result=?,error=?,finished_at=?,updated_at=?,notify=1 WHERE id=?',
                       (status, json.dumps(result) if result is not None else None, error, time.time(), time.time(), job_id))

    def cancel(self, job_id, user_id):
        with self.db() as db:
            return db.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=? AND user_id=? AND status='queued'",
                              (time.time(), job_id, user_id)).rowcount == 1

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='Bot đã dừng giữa chừng; dùng /retry để chạy lại.',notify=1 WHERE status='running'")

    def retry(self, job_id, user_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=? AND user_id=?', (job_id, user_id)).fetchone()
            if row is None or row['status'] not in {'failed', 'interrupted'}:
                return False
            duplicate = db.execute("SELECT 1 FROM jobs WHERE profile=? AND chapter=? AND status IN ('queued','running','succeeded')",
                                   (row['profile'], row['chapter'])).fetchone()
            if duplicate:
                return False
            db.execute("UPDATE jobs SET status='queued',run_at=?,progress='{}',error=NULL,result=NULL,started_at=NULL,finished_at=NULL,notify=0 WHERE id=?",
                       (time.time(), job_id))
            return True

    def notifications(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs WHERE notify=1 ORDER BY id LIMIT 20')]

    def notified(self, job_id, message_id, version):
        with self.db() as db:
            db.execute('UPDATE jobs SET message_id=?,notify=CASE WHEN updated_at=? THEN 0 ELSE notify END WHERE id=?',
                       (message_id, version, job_id))

    def historical_duration(self, profile):
        with self.db() as db:
            rows = db.execute("SELECT finished_at-started_at FROM jobs WHERE profile=? AND status='succeeded' ORDER BY id DESC LIMIT 10",
                              (profile,)).fetchall()
            return sum(r[0] for r in rows) / len(rows) if rows else None
