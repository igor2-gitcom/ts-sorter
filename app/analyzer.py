"""Анализ MPEG-2 TS: ffprobe -> проверка читаемости, OpenCV+YOLO -> люди/техника."""
import os, json, subprocess, shutil, time, datetime, logging, cv2
from ultralytics import YOLO
from . import db
log = logging.getLogger("analyzer")
DATA = os.environ.get("DATA_DIR", "/data")
INCOMING = os.path.join(DATA, "incoming")
FOLDERS = {"people": "1_people", "vehicles": "2_vehicles", "unreadable": "3_unreadable", "other": "4_other"}
SAMPLE_SEC = float(os.environ.get("SAMPLE_SEC", 1.0)); CONF = float(os.environ.get("CONF", 0.45))
MODE = os.environ.get("SORT_MODE", "link")
PERSON = {0: "person"}
VEHICLE = {1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane", 5: "bus", 6: "train", 7: "truck", 8: "boat"}
GAP = 3.0  # сек: детекции ближе этого сливаются в одно событие
_model = None
def model():
    global _model
    if _model is None: _model = YOLO("yolov8n.pt")   # замените на свою модель (yolo11n.pt, кастомная техника)
    return _model

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True, timeout=60)
    if r.returncode: raise RuntimeError(r.stderr.strip()[:300] or "ffprobe error")
    info = json.loads(r.stdout)
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])): raise RuntimeError("нет видеопотока")
    return float(info.get("format", {}).get("duration") or 0)

def detect(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened(): raise RuntimeError("OpenCV не открыл файл")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25; step = max(1, int(round(fps * SAMPLE_SEC)))
    hits, n, ok_frames = [], 0, 0
    while True:
        if not cap.grab(): break
        if n % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                ok_frames += 1; t = n / fps
                for b in model()(frame, conf=CONF, verbose=False)[0].boxes:
                    c = int(b.cls); kind = "person" if c in PERSON else "vehicle" if c in VEHICLE else None
                    if kind: hits.append((kind, PERSON.get(c) or VEHICLE[c], t, float(b.conf)))
        n += 1
    cap.release()
    if ok_frames == 0: raise RuntimeError("не декодировано ни одного кадра")
    return hits

def merge(hits):
    ev = {}
    for kind, label, t, conf in sorted(hits, key=lambda h: h[2]):
        lst = ev.setdefault((kind, label), [])
        if lst and t - lst[-1][1] <= GAP: lst[-1][1] = t; lst[-1][2] = max(lst[-1][2], conf)
        else: lst.append([t, t, conf])
    return [(k, l, a, b, c) for (k, l), v in ev.items() for a, b, c in v]

def place(src, cat):
    d = os.path.join(DATA, FOLDERS[cat]); os.makedirs(d, exist_ok=True); dst = os.path.join(d, os.path.basename(src))
    if os.path.exists(dst): return dst
    if MODE == "move": shutil.move(src, dst)
    else:
        try: os.link(src, dst)
        except OSError: shutil.copy2(src, dst)
    return dst

def process(path):
    name = os.path.basename(path)
    fid = db.x("INSERT OR IGNORE INTO files(name,src,size) VALUES(?,?,?)", (name, path, os.path.getsize(path)))
    fid = db.q("SELECT id FROM files WHERE name=?", (name,))[0]["id"]
    db.x("DELETE FROM events WHERE file_id=?", (fid,))
    err, dur, events = None, None, []
    try:
        dur = probe(path); events = merge(detect(path))
        kinds = {e[0] for e in events}
        cat = "people" if "person" in kinds else "vehicles" if "vehicle" in kinds else "other"
    except Exception as e:
        cat, err = "unreadable", str(e)
    for k, l, a, b, c in events:
        db.x("INSERT INTO events(file_id,kind,label,t_start,t_end,conf) VALUES(?,?,?,?,?,?)", (fid, k, l, a, b, c))
    dst = place(path, cat)
    db.x("UPDATE files SET category=?,dst=?,duration=?,error=?,analyzed_at=? WHERE id=?",
         (cat, dst, dur, err, datetime.datetime.now().isoformat(timespec="seconds"), fid))
    log.info("%s -> %s (%d событий) %s", name, cat, len(events), err or "")

def stable(p):  # файл не дописывается
    s = os.path.getsize(p); time.sleep(2); return s == os.path.getsize(p)

def loop():
    os.makedirs(INCOMING, exist_ok=True); interval = int(os.environ.get("SCAN_INTERVAL", 30))
    while True:
        done = {r["name"] for r in db.q("SELECT name FROM files WHERE category!='pending'")}
        for root, _, fs in os.walk(INCOMING):
            for f in sorted(fs):
                if f.lower().endswith((".ts", ".m2ts", ".mts")) and f not in done:
                    p = os.path.join(root, f)
                    db.x("INSERT OR IGNORE INTO files(name,src,size) VALUES(?,?,?)", (f, p, os.path.getsize(p)))
                    if stable(p):
                        try: process(p)
                        except Exception: log.exception("fail %s", p)
        time.sleep(interval)
