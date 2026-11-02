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
                    run_at REAL NOT NULL, publish_at REAL, status TEXT NOT NULL DEFAULT 'queued',
                    progress TEXT NOT NULL DEFAULT '{}', result TEXT, error TEXT,
                    started_at REAL, finished_at REAL, message_id INTEGER,
                    notify INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS active_chapter ON jobs(profile, chapter)
                    WHERE status IN ('queued','running','succeeded');
                CREATE TABLE IF NOT EXISTS receipts(update_id INTEGER PRIMARY KEY, reply TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS daily_requests (
                    request_id INTEGER PRIMARY KEY, job_ids TEXT NOT NULL);
            ''')
            if 'publish_at' not in {row[1] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute('ALTER TABLE jobs ADD COLUMN publish_at REAL')
                from src.publishing.schedule import parse_publish_at
                for row in db.execute('SELECT id,settings FROM jobs').fetchall():
                    value = json.loads(row['settings']).get('youtube_publish_at')
                    if value:
                        db.execute('UPDATE jobs SET publish_at=? WHERE id=?', (parse_publish_at(value).timestamp(), row['id']))
            db.execute('CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status,run_at,publish_at)')

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
            existing = db.execute("SELECT * FROM jobs WHERE profile=? AND chapter=? AND status IN ('queued','running','succeeded','failed','interrupted') ORDER BY CASE WHEN status IN ('queued','running','succeeded') THEN 0 ELSE 1 END,id DESC LIMIT 1",
                                  (profile, chapter)).fetchone()
            if existing:
                return dict(existing), False
            cursor = db.execute('''INSERT INTO jobs(profile,chapter,settings,user_id,chat_id,run_at,updated_at)
                VALUES (?,?,?,?,?,?,?)''', (profile, chapter, json.dumps(settings), user_id, chat_id, run_at, time.time()))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (cursor.lastrowid,)).fetchone()), True

    def enqueue_daily(self, request_id, profile, plan, settings, user_id, chat_id):
        """Create all jobs atomically, or none. Re-delivery returns the same group."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT job_ids FROM daily_requests WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                ids = json.loads(prior[0])
                return [dict(db.execute('SELECT * FROM jobs WHERE id=?', (i,)).fetchone()) for i in ids]
            for chapter, publish_at in plan:
                if db.execute("SELECT 1 FROM jobs WHERE profile=? AND chapter=? AND status IN ('queued','running','succeeded','failed','interrupted')",
                              (profile, chapter)).fetchone():
                    raise ValueError(f'Chương {chapter} đã có job; không tạo lịch một phần.')
            rows = []
            for chapter, publish_at in plan:
                job_settings = dict(settings, youtube_publish_at=publish_at, youtube_privacy='private')
                now = time.time()
                from src.publishing.schedule import parse_publish_at
                deadline = parse_publish_at(publish_at).timestamp()
                cursor = db.execute('''INSERT INTO jobs(profile,chapter,settings,user_id,chat_id,run_at,updated_at,publish_at)
                    VALUES (?,?,?,?,?,?,?,?)''', (profile, chapter, json.dumps(job_settings), user_id, chat_id, now, now, deadline))
                rows.append(dict(db.execute('SELECT * FROM jobs WHERE id=?', (cursor.lastrowid,)).fetchone()))
            db.execute('INSERT INTO daily_requests VALUES (?,?)', (request_id, json.dumps([row['id'] for row in rows])))
            return rows

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
            row = db.execute("SELECT * FROM jobs WHERE status='queued' AND run_at<=? ORDER BY CASE WHEN publish_at IS NULL THEN run_at ELSE publish_at END,id LIMIT 1",
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
