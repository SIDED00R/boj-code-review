"""
FastAPI 웹 서버 — 앱 초기화 및 라우터 등록만 담당
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

import db
from routes import auth, review, problem, execute, recommend, history, solved, import_routes, stats, cf_submit

app = FastAPI(title="알고리즘 코드 리뷰 & 문제 추천")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

db.init_db()

app.include_router(auth.router)
app.include_router(review.router)
app.include_router(problem.router)
app.include_router(execute.router)
app.include_router(recommend.router)
app.include_router(history.router)
app.include_router(solved.router)
app.include_router(import_routes.router)
app.include_router(stats.router)
app.include_router(cf_submit.router)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
