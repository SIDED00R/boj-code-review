"""
FastAPI 웹 서버
"""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import db
import api_client
import analyzer
import recommender

app = FastAPI(title="백준 코드 리뷰 & 문제 추천")

# static 폴더 마운트
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

db.init_db()


# ──────────────────────────────────────────────
# Request / Response 모델
# ──────────────────────────────────────────────

class ReviewRequest(BaseModel):
    problem_id: int
    code: str


class ImportRequest(BaseModel):
    boj_id: str
    session_cookie: str | None = None
    max_pages: int = 5


class GithubImportRequest(BaseModel):
    repo: str            # "owner/repo"
    token: str | None = None


class ReviewResponse(BaseModel):
    problem_id: int
    title: str
    tier: int
    tier_name: str
    tags: list[str]
    efficiency: str
    complexity: str
    better_algorithm: str | None
    feedback: str
    strengths: list[str]
    weaknesses: list[str]


# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/review", response_model=ReviewResponse)
def review_code(req: ReviewRequest):
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    if not req.code.strip():
        raise HTTPException(status_code=400, detail="코드가 비어있습니다.")

    # DB 캐시 우선 조회 (reviews → solved_history 순)
    problem_info = None
    cached = db.get_cached_problem_info(req.problem_id)
    if cached:
        problem_info = cached
    else:
        try:
            problem_info = api_client.get_problem_info(req.problem_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"문제 정보를 가져올 수 없습니다: {e}")

    statement = api_client.get_problem_statement(req.problem_id)

    try:
        result = analyzer.analyze_code(problem_info, statement, req.code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    db.save_review(
        problem_id=req.problem_id,
        title=problem_info["title"],
        tier=problem_info["tier"],
        tags=problem_info["tags"],
        code=req.code,
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=result.get("complexity", ""),
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )

    return ReviewResponse(
        problem_id=req.problem_id,
        title=problem_info["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem_info["tags"],
        efficiency=result["efficiency"],
        complexity=result.get("complexity", "N/A"),
        better_algorithm=result.get("better_algorithm"),
        feedback=result.get("feedback", ""),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )


@app.get("/api/reviews")
def list_reviews(limit: int = 50):
    history = db.get_review_history(limit)
    for r in history:
        r["tier_name"] = api_client.TIER_NAMES.get(r["tier"], "?")
    return {"reviews": history}


@app.get("/api/reviews/grouped")
def list_reviews_grouped():
    problems = db.get_problems_grouped()
    for p in problems:
        p["tier_name"] = api_client.TIER_NAMES.get(p["tier"], "?")
    return {"problems": problems}


@app.get("/api/reviews/problem/{problem_id}")
def get_reviews_by_problem(problem_id: int):
    reviews = db.get_reviews_by_problem(problem_id)
    for r in reviews:
        r["tier_name"] = api_client.TIER_NAMES.get(r["tier"], "?")
    return {"reviews": reviews}


@app.get("/api/reviews/{review_id}")
def get_review(review_id: int):
    review = db.get_review_detail(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다.")
    review["tier_name"] = api_client.TIER_NAMES.get(review["tier"], "?")
    return review


@app.get("/api/recommend")
def get_recommendations():
    avg_tier = db.get_average_tier()
    weak_tags = recommender.get_weak_tags_scored(5)

    if not weak_tags:
        return {"avg_tier": avg_tier, "tier_name": api_client.TIER_NAMES.get(int(avg_tier), "N/A"),
                "weak_tags": [], "recommendations": []}

    recs = recommender.get_recommendations(top_weak_tags=3)
    tier_desc = recommender.tier_range_description(avg_tier)

    return {
        "avg_tier": avg_tier,
        "tier_name": api_client.TIER_NAMES.get(int(avg_tier), "N/A"),
        "tier_range": tier_desc,
        "weak_tags": weak_tags,
        "recommendations": recs,
    }


@app.get("/api/tier-history")
def get_tier_history():
    rows = db.get_tier_history()
    for r in rows:
        r["tier_name"] = api_client.TIER_NAMES.get(r["tier"], "?")
    return {"history": rows}


@app.get("/api/stats")
def get_stats():
    tag_stats = db.get_tag_stats()
    history = db.get_review_history(20)

    for r in history:
        r["tier_name"] = api_client.TIER_NAMES.get(r["tier"], "?")

    avg_tier = db.get_average_tier()

    return {
        "avg_tier": avg_tier,
        "avg_tier_name": api_client.TIER_NAMES.get(int(avg_tier), "N/A"),
        "total_reviews": len(history),
        "tag_stats": tag_stats,
        "history": history,
    }


@app.post("/api/import-github")
def import_from_github(req: GithubImportRequest):
    """BaekjoonHub GitHub 저장소에서 풀이 기록 가져오기"""
    repo = req.repo.strip()
    if not repo or "/" not in repo:
        raise HTTPException(status_code=400, detail="저장소 주소를 owner/repo 형식으로 입력하세요.")

    try:
        problems = api_client.get_baekjoonhub_problems(repo, req.token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub API 오류: {e}")

    if not problems:
        raise HTTPException(status_code=404, detail="백준 풀이 파일을 찾을 수 없습니다. BaekjoonHub 저장소가 맞는지 확인하세요.")

    existing_ids = db.get_solved_problem_ids()
    new_problems = [p for p in problems if p["problem_id"] not in existing_ids]
    skipped = len(problems) - len(new_problems)
    imported, failed = 0, []

    if new_problems:
        new_ids = [p["problem_id"] for p in new_problems]
        info_map = api_client.get_problems_bulk(new_ids)

        for p in new_problems:
            problem_id = p["problem_id"]
            info = info_map.get(problem_id)
            if not info:
                failed.append(problem_id)
                continue

            code = ""
            try:
                code = api_client.get_raw_github_content(repo, p["path"], req.token)
            except Exception:
                pass

            db.save_solved_problem(
                problem_id=problem_id,
                title=info["title"],
                tier=info["tier"],
                tags=info["tags"],
                code=code,
                language=p.get("language", ""),
            )
            imported += 1

    return {
        "total_found": len(problems),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }


@app.post("/api/import")
def import_history(req: ImportRequest):
    """BOJ 제출 기록 가져오기 (세션 쿠키 선택)"""
    if not req.boj_id.strip():
        raise HTTPException(status_code=400, detail="BOJ 아이디를 입력하세요.")

    try:
        submissions = api_client.get_user_submissions(req.boj_id.strip(), req.max_pages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제출 기록 크롤링 실패: {e}")

    existing_ids = db.get_solved_problem_ids()
    new_subs = [s for s in submissions if s["problem_id"] not in existing_ids]
    skipped = len(submissions) - len(new_subs)
    imported, failed = 0, []

    if new_subs:
        # 문제 정보 한 번에 조회 (bulk)
        new_ids = [s["problem_id"] for s in new_subs]
        info_map = api_client.get_problems_bulk(new_ids)

        for sub in new_subs:
            problem_id = sub["problem_id"]
            info = info_map.get(problem_id)
            if not info:
                failed.append(problem_id)
                continue

            code = ""
            if req.session_cookie:
                code = api_client.get_submission_code(sub["submission_id"], req.session_cookie) or ""

            db.save_solved_problem(
                problem_id=problem_id,
                title=info["title"],
                tier=info["tier"],
                tags=info["tags"],
                code=code,
                language=sub.get("language", ""),
            )
            imported += 1

    return {
        "total_found": len(submissions),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }


@app.post("/api/review-imported/{problem_id}")
def review_imported(problem_id: int):
    """가져온 기록에서 AI 리뷰 요청"""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    problem = db.get_solved_problem(problem_id)
    if not problem:
        raise HTTPException(status_code=404, detail="가져온 기록에서 해당 문제를 찾을 수 없습니다.")
    if not problem.get("code"):
        raise HTTPException(status_code=400, detail="저장된 코드가 없습니다. 세션 쿠키로 다시 가져오기 해주세요.")

    problem_info = {
        "id": problem_id,
        "title": problem["title"],
        "tier": problem["tier"],
        "tier_name": api_client.TIER_NAMES.get(problem["tier"], "?"),
        "tags": problem["tags"],
    }
    statement = api_client.get_problem_statement(problem_id)

    try:
        result = analyzer.analyze_code(problem_info, statement, problem["code"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    db.save_review(
        problem_id=problem_id,
        title=problem["title"],
        tier=problem["tier"],
        tags=problem["tags"],
        code=problem["code"],
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=result.get("complexity", ""),
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )
    # 리뷰 완료 후 가져온 기록에서 제거 (이중 표시 방지)
    db.delete_solved_problem(problem_id)

    return ReviewResponse(
        problem_id=problem_id,
        title=problem["title"],
        tier=problem["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem["tags"],
        efficiency=result["efficiency"],
        complexity=result.get("complexity", "N/A"),
        better_algorithm=result.get("better_algorithm"),
        feedback=result.get("feedback", ""),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )


@app.delete("/api/solved-history/{problem_id}")
def delete_solved_history(problem_id: int):
    db.delete_solved_problem(problem_id)
    return {"ok": True}


@app.delete("/api/solved-history")
def clear_solved_history():
    db.clear_solved_history()
    return {"ok": True}


@app.get("/api/solved-history/{problem_id}")
def get_solved_history_detail(problem_id: int):
    p = db.get_solved_problem(problem_id)
    if not p:
        raise HTTPException(status_code=404, detail="없음")
    return {"code": p.get("code", "")}


@app.get("/api/solved-history")
def get_solved_history():
    rows = db.get_solved_history()
    for r in rows:
        r["tier_name"] = api_client.TIER_NAMES.get(r["tier"], "?")
    return {"problems": rows}


@app.get("/api/report")
def get_report():
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    tag_stats = db.get_tag_stats()
    history = db.get_review_history(10)

    if not tag_stats:
        raise HTTPException(status_code=400, detail="아직 저장된 기록이 없습니다.")

    try:
        report = analyzer.get_cumulative_analysis(tag_stats, history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 생성 실패: {e}")

    return {"report": report}
