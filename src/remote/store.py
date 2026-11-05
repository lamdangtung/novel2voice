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
                CREATE TABLE IF NOT EXISTS ui_sessions(user_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ui_receipts(update_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
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
            if 'cleared' not in {row[1] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute('ALTER TABLE jobs ADD COLUMN cleared INTEGER NOT NULL DEFAULT 0')
            if 'manual_now' not in {row[1] for row in db.execute('PRAGMA table_info(jobs)')}:
                db.execute('ALTER TABLE jobs ADD COLUMN manual_now INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status,run_at,publish_at)')
            db.execute("UPDATE jobs SET run_at=MAX(run_at,publish_at-86400) WHERE status='queued' AND publish_at IS NOT NULL AND manual_now=0")
            # Recover a channel limit reported before this guard was installed.
            latest = db.execute("SELECT MAX(finished_at) FROM jobs WHERE status='failed' AND error LIKE '%uploadLimitExceeded%'").fetchone()[0]
            if latest and latest + 86400 > time.time():
                previous = db.execute("SELECT value FROM settings WHERE key='upload_pause_until'").fetchone()
                until = max(latest + 86400, float(previous[0]) if previous else 0)
                db.execute("INSERT INTO settings VALUES ('upload_pause_until',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(until),))


    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ui_state(self, user_id):
        with self.db() as db:
            row = db.execute('SELECT payload FROM ui_sessions WHERE user_id=?', (user_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def ui_receipt(self, update_id):
        with self.db() as db:
            row = db.execute('SELECT payload FROM ui_receipts WHERE update_id=?', (update_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def ui_commit(self, user_id, state, update_id, response):
        """Persist a wizard transition and its reply together, safe on redelivery."""
        with self.db() as db:
            db.execute('INSERT INTO ui_sessions VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload',
                       (user_id, json.dumps(state)))
            db.execute('INSERT OR IGNORE INTO ui_receipts VALUES (?,?)', (update_id, json.dumps(response)))

    def offset(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='offset'").fetchone()
            return int(row[0]) if row else 0

    def set_offset(self, offset):
        with self.db() as db:
            db.execute("INSERT INTO settings VALUES ('offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(offset),))

    def pause_uploads(self, until):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='upload_pause_until'").fetchone()
            until = max(until, float(row[0]) if row else 0)
            db.execute("INSERT INTO settings VALUES ('upload_pause_until',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(until),))

    def upload_pause_until(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='upload_pause_until'").fetchone()
            return float(row[0]) if row else 0

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
                db.execute("UPDATE jobs SET cleared=0 WHERE id=?", (existing["id"],))
                return dict(existing, cleared=0), False
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
                    VALUES (?,?,?,?,?,?,?,?)''', (profile, chapter, json.dumps(job_settings), user_id, chat_id, max(now, deadline - 24 * 3600), now, deadline))
                rows.append(dict(db.execute('SELECT * FROM jobs WHERE id=?', (cursor.lastrowid,)).fetchone()))
            db.execute('INSERT INTO daily_requests VALUES (?,?)', (request_id, json.dumps([row['id'] for row in rows])))
            return rows

    def get(self, job_id, user_id=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?' + (' AND user_id=?' if user_id is not None else ''),
                             (job_id, user_id) if user_id is not None else (job_id,)).fetchone()
            return dict(row) if row else None

    def list(self, user_id):
        return self.list_page(user_id, 1)[0]

    def list_page(self, user_id, page=1, page_size=10, *, group="all"):
        if page < 1 or not 1 <= page_size <= 10:
            raise ValueError('Trang phải >= 1; kích thước trang từ 1 đến 10.')
        groups = {'all': (), 'active': ('queued', 'running'), 'failed': ('failed', 'interrupted'),
                  'done': ('succeeded', 'cancelled')}
        if group not in groups:
            raise ValueError('Bộ lọc không hợp lệ.')
        statuses = groups[group]
        where = 'user_id=? AND cleared=0'
        params = [user_id]
        if statuses:
            where += ' AND status IN (' + ','.join('?' for _ in statuses) + ')'
            params.extend(statuses)
        with self.db() as db:
            # Count and rows share one snapshot while the worker updates jobs.
            db.execute('BEGIN')
            total = db.execute('SELECT COUNT(*) FROM jobs WHERE ' + where, params).fetchone()[0]
            pages = max(1, (total + page_size - 1) // page_size)
            if page > pages:
                return [], total
            rows = db.execute('SELECT * FROM jobs WHERE ' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?',
                              (*params, page_size, (page - 1) * page_size))
            return [dict(row) for row in rows], total

    def claim(self, now=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = time.time() if now is None else now
            pause = db.execute("SELECT value FROM settings WHERE key='upload_pause_until'").fetchone()
            pause_until = float(pause[0]) if pause else 0
            candidates = db.execute("SELECT * FROM jobs WHERE status='queued' AND run_at<=? ORDER BY manual_now DESC,CASE WHEN manual_now=1 OR publish_at IS NULL THEN run_at ELSE publish_at END,id", (current,)).fetchall()
            row = next((candidate for candidate in candidates
                        if candidate['manual_now'] or pause_until <= current or not json.loads(candidate['settings']).get('upload_youtube', True)), None)
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

    def clear(self, target, user_id):
        """Hide terminal jobs; retain IDs and checkpoints for safe deduplication."""
        groups = {'finished': ('succeeded', 'cancelled'),
                  'failed': ('failed', 'interrupted')}
        statuses = groups.get(target, ('succeeded', 'cancelled', 'failed', 'interrupted'))
        placeholders = ','.join('?' for _ in statuses)
        query = f'UPDATE jobs SET cleared=1,notify=0 WHERE user_id=? AND cleared=0 AND status IN ({placeholders})'
        params = [user_id, *statuses]
        if target not in groups:
            query += ' AND id=?'
            params.append(int(target))
        with self.db() as db:
            return db.execute(query, params).rowcount

    def recover(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='Bot đã dừng giữa chừng; dùng /retry để chạy lại.',notify=1 WHERE status='running'")

    def retry(self, job_id, user_id, *, publish_at=None, immediate=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=? AND user_id=?', (job_id, user_id)).fetchone()
            if row is None or row['status'] not in ({'queued', 'failed', 'interrupted'} if immediate else {'failed', 'interrupted'}):
                return False
            duplicate = db.execute("SELECT 1 FROM jobs WHERE profile=? AND chapter=? AND status IN ('queued','running','succeeded') AND id!=?",
                                   (row['profile'], row['chapter'], job_id)).fetchone()
            if duplicate:
                return False
            settings = json.loads(row['settings'])
            deadline = row['publish_at']
            if deadline is None and settings.get('youtube_publish_at'):
                from src.publishing.schedule import parse_publish_at
                deadline = parse_publish_at(settings['youtube_publish_at']).timestamp()
            if immediate:
                settings.pop('youtube_publish_at', None)
                settings.update(youtube_privacy='private', manual_upload_now=True)
                deadline = None
            elif publish_at is not None:
                if not settings.get('upload_youtube', True):
                    raise ValueError('Profile này tắt upload YouTube.')
                from src.publishing.schedule import require_future, parse_publish_at, normalize_publish_at
                require_future(publish_at, buffer_seconds=900)
                settings.update(youtube_publish_at=normalize_publish_at(publish_at), youtube_privacy='private')
                deadline = parse_publish_at(publish_at).timestamp()
            elif deadline:
                from src.publishing.schedule import require_future
                require_future(settings['youtube_publish_at'], buffer_seconds=900)
            if not immediate:
                settings.pop('manual_upload_now', None)
            db.execute('UPDATE jobs SET settings=?,publish_at=?,manual_now=? WHERE id=?', (json.dumps(settings), deadline, int(immediate), job_id))
            run_at = max(time.time(), deadline - 86400 if deadline else 0)
            db.execute("UPDATE jobs SET status='queued',cleared=0,run_at=?,progress='{}',error=NULL,result=NULL,started_at=NULL,finished_at=NULL,notify=0 WHERE id=?",
                       (run_at, job_id))
            return True

    def is_notification_message(self, chat_id, message_id):
        with self.db() as db:
            return db.execute('SELECT 1 FROM jobs WHERE chat_id=? AND message_id=? LIMIT 1',
                              (chat_id, message_id)).fetchone() is not None

    def summary(self, user_id):
        with self.db() as db:
            return dict(db.execute('SELECT status,COUNT(*) FROM jobs WHERE user_id=? AND cleared=0 GROUP BY status',
                                   (user_id,)).fetchall())

    def notifications(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs WHERE notify=1 AND cleared=0 ORDER BY id LIMIT 20')]

    def notified(self, job_id, message_id, version):
        with self.db() as db:
            db.execute('UPDATE jobs SET message_id=?,notify=CASE WHEN updated_at=? THEN 0 ELSE notify END WHERE id=?',
                       (message_id, version, job_id))

    def historical_duration(self, profile):
        with self.db() as db:
            rows = db.execute("SELECT finished_at-started_at FROM jobs WHERE profile=? AND status='succeeded' ORDER BY id DESC LIMIT 10",
                              (profile,)).fetchall()
            return sum(r[0] for r in rows) / len(rows) if rows else None
