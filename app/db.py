import sqlite3, os, threading
DB = os.path.join(os.environ.get("DATA_DIR", "/data"), "index.db")
_lock = threading.Lock()
def conn():
    c = sqlite3.connect(DB, check_same_thread=False); c.row_factory = sqlite3.Row; return c
def init():
    with _lock, conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, name TEXT UNIQUE, src TEXT, dst TEXT,
          size INTEGER, duration REAL, category TEXT DEFAULT 'pending', error TEXT, analyzed_at TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, file_id INTEGER, kind TEXT, label TEXT,
          t_start REAL, t_end REAL, conf REAL);
        CREATE INDEX IF NOT EXISTS ev_f ON events(file_id);""")
def q(sql, args=()):
    with _lock, conn() as c: return [dict(r) for r in c.execute(sql, args).fetchall()]
def x(sql, args=()):
    with _lock, conn() as c: cur = c.execute(sql, args); return cur.lastrowid
