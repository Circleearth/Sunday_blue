"""Small shared transaction boundary and durable events; no role-owned deletion."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def day(at=None):
    local=(at or datetime.now().astimezone()).astimezone(timezone(timedelta(hours=8)))
    return (local-timedelta(hours=4)).date().isoformat()


def next_boundary(at):
    local=at.astimezone(timezone(timedelta(hours=8)))
    boundary=local.replace(hour=4,minute=0,second=0,microsecond=0)
    return boundary if local<boundary else boundary+timedelta(days=1)

def record_interval(conn, run_id, start, end):
    while start < end:
        stop=min(end,next_boundary(start))
        seconds=(stop-start).total_seconds()
        conn.execute('INSERT INTO focus_day_slices VALUES(?,?,?) ON CONFLICT(run_id,day) DO UPDATE SET seconds=seconds+excluded.seconds',(run_id,day(start),seconds))
        start=stop

class ModuleDB:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root/'data/modules.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS module_events (
                    seq INTEGER PRIMARY KEY, event_key TEXT UNIQUE, kind TEXT, payload TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS module_settings (key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS module_receipts (
                    consumer TEXT, event_key TEXT, PRIMARY KEY(consumer,event_key));''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def emit(db, key, kind, payload):
        db.execute('INSERT OR IGNORE INTO module_events(event_key,kind,payload,created) VALUES(?,?,?,?)',
                   (key,kind,json.dumps(payload,ensure_ascii=False),stamp()))

    def events(self, consumer, limit=50):
        with self.connect() as db:
            return [dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('''SELECT * FROM module_events e
                WHERE NOT EXISTS(SELECT 1 FROM module_receipts r WHERE r.event_key=e.event_key AND r.consumer=?)
                ORDER BY seq LIMIT ?''',(consumer,limit))]

    @staticmethod
    def receipt(db, consumer, key):
        db.execute('INSERT OR IGNORE INTO module_receipts VALUES(?,?)',(consumer,key))

    def get(self, key, default=None):
        with self.connect() as db: row=db.execute('SELECT value FROM module_settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT INTO module_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key,json.dumps(value,ensure_ascii=False)))
