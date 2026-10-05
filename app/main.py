import os, threading, subprocess, logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from . import db, analyzer
logging.basicConfig(level=logging.INFO)
app = FastAPI(title="TS archive sorter")
ST = os.path.join(os.path.dirname(__file__), "static")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=ST), name="static")

@app.on_event("startup")
def start():
    db.init(); threading.Thread(target=analyzer.loop, daemon=True).start()

@app.get("/")
def index(): return FileResponse(os.path.join(ST, "index.html"))
@app.get("/report")
def report(): return FileResponse(os.path.join(ST, "report.html"))

@app.get("/api/files")
def files(category: str = Query("all")):
    sql = "SELECT f.*, (SELECT COUNT(*) FROM events e WHERE e.file_id=f.id AND kind='person') persons, " \
          "(SELECT COUNT(*) FROM events e WHERE e.file_id=f.id AND kind='vehicle') vehicles FROM files f"
    return db.q(sql + ("" if category == "all" else " WHERE category=?") + " ORDER BY name",
                () if category == "all" else (category,))

@app.get("/api/events")
def events(kind: str = "all"):
    sql = "SELECT e.*, f.name, f.category FROM events e JOIN files f ON f.id=e.file_id"
    return db.q(sql + ("" if kind == "all" else " WHERE e.kind=?") + " ORDER BY f.name, e.t_start",
                () if kind == "all" else (kind,))

@app.post("/api/rescan/{fid}")
def rescan(fid: int):
    db.x("UPDATE files SET category='pending' WHERE id=?", (fid,)); return {"ok": True}

def _file(fid):
    r = db.q("SELECT * FROM files WHERE id=?", (fid,))
    if not r: raise HTTPException(404)
    p = r[0]["dst"] or r[0]["src"]
    if not os.path.exists(p): p = r[0]["src"]
    if not os.path.exists(p): raise HTTPException(404, "файл отсутствует")
    return p

@app.get("/media/{fid}")          # скачать исходный .ts
def media(fid: int):
    p = _file(fid); return FileResponse(p, media_type="video/mp2t", filename=os.path.basename(p))

@app.get("/play/{fid}")           # ремукс TS -> fMP4 «на лету» для браузера, с позиции t
def play(fid: int, t: float = 0):
    p = _file(fid)
    cmd = ["ffmpeg", "-v", "error", "-ss", str(max(0, t)), "-i", p, "-map", "0:v:0", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-movflags", "frag_keyframe+empty_moov",
           "-f", "mp4", "pipe:1"]   # если видео уже H.264 — можно -c:v copy
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    def gen():
        try:
            while chunk := proc.stdout.read(64 * 1024): yield chunk
        finally: proc.kill()
    return StreamingResponse(gen(), media_type="video/mp4")
