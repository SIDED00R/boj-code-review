"""
FastAPI 웹 서버
"""
import os
import time
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

app = FastAPI(title="알고리즘 코드 리뷰 & 문제 추천")

# static 폴더 마운트
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

db.init_db()


# ──────────────────────────────────────────────
# Request / Response 모델
# ──────────────────────────────────────────────

class ReviewRequest(BaseModel):
    platform: str = "boj"
    problem_id: int | None = None
    problem_ref: str | None = None
    problem_statement: str | None = None
    code: str


class ImportRequest(BaseModel):
    boj_id: str
    session_cookie: str | None = None
    max_pages: int = 5


class GithubImportRequest(BaseModel):
    repo: str            # "owner/repo"
    token: str | None = None


class CodeforcesImportRequest(BaseModel):
    handle: str
    count: int = 200
    api_key: str | None = None
    api_secret: str | None = None


class ReviewResponse(BaseModel):
    problem_id: int
    platform: str
    problem_ref: str
    problem_url: str
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


def _resolve_problem(platform: str, problem_id: int | None, problem_ref: str | None,
                     custom_statement: str | None = None) -> tuple[dict, str]:
    platform = (platform or "boj").strip().lower()
    if platform not in {"boj", "codeforces"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다. 'boj' 또는 'codeforces'만 가능합니다.")

    if platform == "codeforces":
        if not (problem_ref or "").strip():
            raise HTTPException(status_code=400, detail="Codeforces 문제 번호를 입력하세요. 예: 4A 또는 4/A")
        try:
            info = api_client.get_codeforces_problem_info(problem_ref.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Codeforces 문제 조회 실패: {e}")
        statement = (custom_statement or "").strip() or api_client.get_codeforces_problem_statement(info["problem_ref"])
        return info, statement

    if problem_id is None:
        raise HTTPException(status_code=400, detail="백준 문제 번호를 입력하세요.")

    info = db.get_cached_problem_info(problem_id)
    if not info:
        try:
            info = api_client.get_problem_info(problem_id)
        except Exception:
            info = {
                "id": problem_id,
                "platform": "boj",
                "problem_ref": str(problem_id),
                "title": f"문제 {problem_id}",
                "tier": 0,
                "tier_name": "Unrated",
                "tags": [],
            }
    info["platform"] = "boj"
    info["problem_ref"] = str(problem_id)
    statement = (custom_statement or "").strip() or api_client.get_problem_statement(problem_id)
    return info, statement


@app.post("/api/review", response_model=ReviewResponse)
def review_code(req: ReviewRequest):
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    if not req.code.strip():
        raise HTTPException(status_code=400, detail="코드가 비어있습니다.")

    problem_info, statement = _resolve_problem(req.platform, req.problem_id, req.problem_ref, req.problem_statement)

    try:
        result = analyzer.analyze_code(problem_info, statement, req.code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    db.save_review(
        problem_id=problem_info["id"],
        title=problem_info["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem_info["tags"],
        code=req.code,
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=result.get("complexity", ""),
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
        platform=problem_info["platform"],
        problem_ref=problem_info["problem_ref"],
    )

    return ReviewResponse(
        problem_id=problem_info["id"],
        platform=problem_info["platform"],
        problem_ref=problem_info["problem_ref"],
        problem_url=api_client.get_problem_url(problem_info["platform"], problem_info["problem_ref"]),
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
    return {"reviews": db.get_review_history(limit)}


@app.get("/api/reviews/grouped")
def list_reviews_grouped():
    return {"problems": db.get_problems_grouped()}


@app.get("/api/reviews/problem/{platform}/{problem_ref}")
def get_reviews_by_problem(platform: str, problem_ref: str):
    return {"reviews": db.get_reviews_by_problem(platform, problem_ref)}


@app.get("/api/reviews/{review_id}")
def get_review(review_id: int):
    review = db.get_review_detail(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다.")
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
    return {"history": db.get_tier_history()}


@app.get("/api/stats")
def get_stats():
    tag_stats = db.get_tag_stats()
    history = db.get_review_history(20)

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
                tier_name=info["tier_name"],
                tags=info["tags"],
                code=code,
                language=p.get("language", ""),
                platform="boj",
                problem_ref=str(problem_id),
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
                tier_name=info["tier_name"],
                tags=info["tags"],
                code=code,
                language=sub.get("language", ""),
                platform="boj",
                problem_ref=str(problem_id),
            )
            imported += 1

    return {
        "total_found": len(submissions),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }


@app.post("/api/import-codeforces")
def import_codeforces_history(req: CodeforcesImportRequest):
    handle = req.handle.strip()
    if not handle:
        raise HTTPException(status_code=400, detail="Codeforces handle을 입력하세요.")

    api_key = (req.api_key or os.environ.get("CODEFORCES_API_KEY") or "").strip() or None
    api_secret = (req.api_secret or os.environ.get("CODEFORCES_API_SECRET") or "").strip() or None
    if bool(api_key) != bool(api_secret):
        raise HTTPException(status_code=400, detail="Codeforces API Key와 Secret은 둘 다 입력하거나 둘 다 비워두세요.")

    try:
        user = api_client.get_codeforces_user_info(handle)
        time.sleep(2.1)
        submissions = api_client.get_codeforces_user_submissions(
            handle,
            count=max(1, min(req.count, 1000)),
            api_key=api_key,
            api_secret=api_secret,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Codeforces 기록 조회 실패: {e}")

    existing_keys = db.get_solved_problem_keys()
    new_subs = [s for s in submissions if ("codeforces", s["problem_ref"]) not in existing_keys]
    skipped = len(submissions) - len(new_subs)

    for sub in new_subs:
        db.save_solved_problem(
            problem_id=0,
            title=sub["title"],
            tier=0,
            tier_name=sub["tier_name"],
            tags=sub["tags"],
            code=sub["code"],
            language=sub.get("language", ""),
            platform="codeforces",
            problem_ref=sub["problem_ref"],
        )

    return {
        "handle": user.get("handle", handle),
        "total_found": len(submissions),
        "imported": len(new_subs),
        "skipped": skipped,
        "has_source": any(bool(s.get("code")) for s in submissions),
    }


@app.post("/api/review-imported/{platform}/{problem_ref}")
def review_imported(platform: str, problem_ref: str):
    """가져온 기록에서 AI 리뷰 요청"""
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    problem = db.get_solved_problem(platform, problem_ref)
    if not problem:
        raise HTTPException(status_code=404, detail="가져온 기록에서 해당 문제를 찾을 수 없습니다.")
    if not problem.get("code"):
        raise HTTPException(status_code=400, detail="저장된 코드가 없습니다. 세션 쿠키로 다시 가져오기 해주세요.")

    if platform == "codeforces":
        problem_info = api_client.get_codeforces_problem_info(problem_ref)
        if problem.get("title"):
            problem_info["title"] = problem["title"]
        statement = api_client.get_codeforces_problem_statement(problem_ref)
    else:
        problem_id = problem["problem_id"]
        problem_info = {
            "id": problem_id,
            "platform": "boj",
            "problem_ref": str(problem_id),
            "title": problem["title"],
            "tier": problem["tier"],
            "tier_name": problem.get("tier_name") or api_client.TIER_NAMES.get(problem["tier"], "?"),
            "tags": problem["tags"],
        }
        statement = api_client.get_problem_statement(problem_id)

    try:
        result = analyzer.analyze_code(problem_info, statement, problem["code"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    db.save_review(
        problem_id=problem_info["id"],
        title=problem["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem["tags"],
        code=problem["code"],
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=result.get("complexity", ""),
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
        platform=platform,
        problem_ref=problem_ref,
    )
    # 리뷰 완료 후 가져온 기록에서 제거 (이중 표시 방지)
    db.delete_solved_problem(platform, problem_ref)

    return ReviewResponse(
        problem_id=problem_info["id"],
        platform=platform,
        problem_ref=problem_ref,
        problem_url=api_client.get_problem_url(platform, problem_ref),
        title=problem["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem["tags"],
        efficiency=result["efficiency"],
        complexity=result.get("complexity", "N/A"),
        better_algorithm=result.get("better_algorithm"),
        feedback=result.get("feedback", ""),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )


@app.delete("/api/solved-history/{platform}/{problem_ref}")
def delete_solved_history(platform: str, problem_ref: str):
    db.delete_solved_problem(platform, problem_ref)
    return {"ok": True}


@app.delete("/api/solved-history")
def clear_solved_history():
    db.clear_solved_history()
    return {"ok": True}


@app.get("/api/solved-history/{platform}/{problem_ref}")
def get_solved_history_detail(platform: str, problem_ref: str):
    p = db.get_solved_problem(platform, problem_ref)
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
