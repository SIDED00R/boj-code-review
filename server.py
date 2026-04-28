"""
FastAPI 웹 서버
"""
import os
import time
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
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
# GitHub push 헬퍼
# ──────────────────────────────────────────────

def _build_readme(platform: str, problem_ref: str, title: str,
                  tier_name: str, tags: list, language: str, url: str,
                  description: str = "", input_desc: str = "", output_desc: str = "") -> str:
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    date_str = f"{now.year}년 {now.month}월 {now.day}일 {now.strftime('%H:%M:%S')}"
    tags_str = ", ".join(f"`{t}`" for t in tags) if tags else "없음"

    lines = [
        f"# [{tier_name}] {title} - {problem_ref}",
        "",
        f"[문제 링크]({url})",
        "",
        "## 성능 요약",
        "",
        "메모리: - KB, 시간: - ms",
        "",
        "## 분류",
        "",
        tags_str,
        "",
        "## 제출 일자",
        "",
        date_str,
    ]
    if description:
        lines += ["", "## 문제 설명", "", description]
    if input_desc:
        lines += ["", "## 입력", "", input_desc]
    if output_desc:
        lines += ["", "## 출력", "", output_desc]
    return "\n".join(lines) + "\n"


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
    github_repo: str | None = None
    github_token: str | None = None


class SetRepoRequest(BaseModel):
    repo: str


class PushReviewRequest(BaseModel):
    platform: str
    problem_ref: str
    title: str
    tier_name: str
    tags: list[str] = []
    code: str
    language: str = ""
    url: str = ""


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

def _github_oauth_settings():
    client_id = os.environ.get("GITHUB_CLIENT_ID", "")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")
    app_url = os.environ.get("APP_URL", "http://localhost:8080")
    return client_id, client_secret, app_url


# ──────────────────────────────────────────────
# GitHub OAuth 엔드포인트
# ──────────────────────────────────────────────

@app.get("/auth/github")
def github_oauth_start():
    client_id, _, app_url = _github_oauth_settings()
    if not client_id:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID가 설정되지 않았습니다.")
    callback_url = f"{app_url}/auth/github/callback"
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&scope=repo&redirect_uri={callback_url}"
    )
    return RedirectResponse(github_url)


@app.get("/auth/github/callback")
def github_oauth_callback(code: str = "", error: str = ""):
    client_id, client_secret, app_url = _github_oauth_settings()
    if error or not code:
        return RedirectResponse(f"{app_url}/?github=error")
    try:
        token = api_client.exchange_github_code(code, client_id, client_secret)
        user = api_client.get_github_user(token)
        username = user.get("login", "")
        db.save_github_settings(access_token=token, github_username=username)
    except Exception as e:
        return RedirectResponse(f"{app_url}/?github=error&msg={str(e)[:80]}")
    return RedirectResponse(f"{app_url}/?github=connected&user={username}")


@app.get("/auth/github/status")
def github_status():
    settings = db.get_github_settings()
    if not settings:
        return {"connected": False}
    return {
        "connected": True,
        "username": settings.get("github_username", ""),
        "target_repo": settings.get("target_repo", ""),
    }


@app.post("/auth/github/repo")
def set_github_repo(req: SetRepoRequest):
    if not db.get_github_settings():
        raise HTTPException(status_code=400, detail="GitHub 연결 먼저 해주세요.")
    repo = req.repo.strip()
    if not repo or "/" not in repo:
        raise HTTPException(status_code=400, detail="저장소를 owner/repo 형식으로 입력하세요.")
    db.update_github_target_repo(repo)
    return {"ok": True, "target_repo": repo}


@app.delete("/auth/github")
def github_disconnect():
    db.delete_github_settings()
    return {"ok": True}


@app.get("/auth/github/repos")
def get_github_repos():
    settings = db.get_github_settings()
    if not settings:
        raise HTTPException(status_code=400, detail="GitHub 연결이 필요합니다.")
    try:
        repos = api_client.get_github_user_repos(settings["access_token"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"레포지토리 조회 실패: {e}")
    return {"repos": repos}


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


@app.post("/api/push-review")
def push_review_to_github(req: PushReviewRequest):
    gh_settings = db.get_github_settings()
    if not gh_settings:
        raise HTTPException(status_code=400, detail="GitHub 연결이 필요합니다. 헤더의 '🐙 GitHub 연결' 버튼을 눌러주세요.")
    github_repo = gh_settings.get("target_repo", "")
    github_token = gh_settings.get("access_token", "")
    if not github_repo or not github_token:
        raise HTTPException(status_code=400, detail="GitHub 저장소를 선택해주세요.")

    ext = api_client._get_file_extension(req.language)
    url = req.url or api_client.get_problem_url(req.platform, req.problem_ref)

    if req.platform == "boj":
        tier_cat = req.tier_name.split()[0] if req.tier_name else "Unrated"
        folder = f"백준/{tier_cat}/{req.problem_ref}번. {req.title}"
        msg = f"[BOJ] {req.problem_ref}번. {req.title}"
        sections = api_client.get_boj_problem_sections(int(req.problem_ref))
    else:
        folder = f"Codeforces/{req.problem_ref}. {req.title}"
        msg = f"[Codeforces] {req.problem_ref}. {req.title}"
        sections = api_client.get_cf_problem_sections(req.problem_ref)

    readme = _build_readme(req.platform, req.problem_ref, req.title,
                           req.tier_name, req.tags, req.language, url,
                           sections.get("description", ""),
                           sections.get("input", ""),
                           sections.get("output", ""))
    api_client.push_file_to_github(github_repo, github_token, f"{folder}/README.md", readme, msg)
    ok = api_client.push_file_to_github(github_repo, github_token,
                                        f"{folder}/{req.problem_ref}{ext}", req.code, msg)
    if not ok:
        raise HTTPException(status_code=500, detail="GitHub push에 실패했습니다.")
    return {"pushed": True, "repo": github_repo, "path": folder}


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
def get_recommendations(platform: str = Query("codeforces")):
    if platform == "codeforces":
        avg_rating = db.get_average_cf_rating()
        avg_tier = 0
        tier_name = f"CF {int(avg_rating)}" if avg_rating != 1200.0 or db.get_solved_cf_refs() else "N/A"
        tier_range = f"CF {max(800, int(avg_rating) - 200)} ~ CF {min(3500, int(avg_rating) + 400)}"
    else:
        avg_tier = db.get_average_tier()
        avg_rating = avg_tier
        tier_name = api_client.TIER_NAMES.get(int(avg_tier), "N/A")
        tier_range = recommender.tier_range_description(avg_tier)

    weak_tags = recommender.get_weak_tags_scored(5, platform=platform)

    if not weak_tags:
        return {"avg_tier": avg_tier, "tier_name": tier_name,
                "weak_tags": [], "recommendations": [], "platform": platform}

    recs = recommender.get_recommendations(top_weak_tags=3, platform=platform)

    return {
        "avg_tier": avg_tier,
        "tier_name": tier_name,
        "tier_range": tier_range,
        "weak_tags": weak_tags,
        "recommendations": recs,
        "platform": platform,
    }


# ──────────────────────────────────────────────
# 코드 실행 (live_webcoding의 spawn 방식을 Python subprocess로 포팅)
# ──────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    code: str
    language: str = "python3"
    stdin: str = ""
    timeout_sec: int = 5


def _run_python(code: str, stdin: str, timeout: int) -> dict:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        r = subprocess.run(
            ["python3", "-c", code],
            input=stdin, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": "[Python3를 찾을 수 없습니다]", "exit_code": -1}


def _run_cpp(code: str, stdin: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "sol.cpp")
        exe = os.path.join(tmpdir, "sol")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            cr = subprocess.run(
                ["g++", "-O2", "-std=c++17", "-o", exe, src],
                capture_output=True, text=True, timeout=30,
            )
        except FileNotFoundError:
            return {"stdout": "", "stderr": "[g++를 찾을 수 없습니다]", "exit_code": -1}
        if cr.returncode != 0:
            return {"stdout": "", "stderr": cr.stderr, "exit_code": cr.returncode}
        try:
            rr = subprocess.run(
                [exe], input=stdin, capture_output=True, text=True, timeout=timeout,
            )
            return {"stdout": rr.stdout, "stderr": rr.stderr, "exit_code": rr.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}


@app.post("/api/execute")
def execute_code(req: ExecuteRequest):
    t0 = time.time()
    lang = req.language.lower()
    if "python" in lang or "pypy" in lang:
        result = _run_python(req.code, req.stdin, req.timeout_sec)
    elif "c++" in lang or "cpp" in lang or "gnu" in lang:
        result = _run_cpp(req.code, req.stdin, req.timeout_sec)
    else:
        raise HTTPException(400, f"지원하지 않는 언어: {req.language}")
    result["time_ms"] = int((time.time() - t0) * 1000)
    return result


# ──────────────────────────────────────────────
# CF 문제 가져오기 + 한글 번역
# ──────────────────────────────────────────────

def _translate_cf_problem(text: str, title: str) -> str:
    try:
        from openai import OpenAI as _OpenAI
        client = _OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "당신은 프로그래밍 문제 번역 전문가입니다. "
                    "Codeforces 문제를 한국어로 번역합니다. "
                    "수식($...$, $$...$$)은 그대로 유지하고, 문제의 의미를 정확하게 전달하세요. "
                    "번역문만 출력하세요."
                )},
                {"role": "user", "content": f"제목: {title}\n\n{text}"},
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[번역 실패: {e}]\n\n{text}"


@app.get("/api/problem/cf/{problem_ref}")
def get_cf_problem(problem_ref: str):
    import re
    import requests as _req
    from bs4 import BeautifulSoup

    m = re.match(r'^(\d+)([A-Za-z]\d*)$', problem_ref.strip())
    if not m:
        raise HTTPException(400, "잘못된 문제 번호 형식 (예: 4A, 1234B)")
    contest_id, index = m.group(1), m.group(2).upper()

    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    try:
        resp = _req.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(502, f"CF 페이지 로딩 실패: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")
    prob_div = soup.find("div", class_="problem-statement")
    if not prob_div:
        raise HTTPException(502, "문제 내용을 찾을 수 없습니다")

    header = prob_div.find("div", class_="header")
    title_el = header.find("div", class_="title") if header else None
    title = title_el.get_text(strip=True) if title_el else f"CF {problem_ref}"
    tl_el = header.find("div", class_="time-limit") if header else None
    ml_el = header.find("div", class_="memory-limit") if header else None
    time_limit = tl_el.get_text(strip=True) if tl_el else ""
    memory_limit = ml_el.get_text(strip=True) if ml_el else ""

    sample_test = prob_div.find("div", class_="sample-test")
    samples = []
    if sample_test:
        inputs = [
            div.find("pre").get_text("\n", strip=True)
            for div in sample_test.find_all("div", class_="input") if div.find("pre")
        ]
        outputs = [
            div.find("pre").get_text("\n", strip=True)
            for div in sample_test.find_all("div", class_="output") if div.find("pre")
        ]
        samples = [{"input": i.strip(), "output": o.strip()} for i, o in zip(inputs, outputs)]
        sample_test.decompose()

    if header:
        header.decompose()

    statement_text = prob_div.get_text("\n", strip=True)
    translated = _translate_cf_problem(statement_text, title)

    return {
        "title": title,
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "statement_ko": translated,
        "samples": samples,
        "url": url,
        "contest_id": contest_id,
        "index": index,
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

    gh_settings = db.get_github_settings()
    github_repo = gh_settings.get("target_repo") if gh_settings else None
    github_token = gh_settings.get("access_token") if gh_settings else None
    github_push_enabled = bool(github_repo and github_token)
    github_pushed = 0

    if new_subs:
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
            if github_push_enabled and code:
                ext = api_client._get_file_extension(sub.get("language", ""))
                tier_cat = info["tier_name"].split()[0] if info.get("tier_name") else "Unrated"
                folder = f"백준/{tier_cat}/{problem_id}번. {info['title']}"
                msg = f"[BOJ] {problem_id}번. {info['title']}"
                boj_url = f"https://www.acmicpc.net/problem/{problem_id}"
                readme = _build_readme("boj", str(problem_id), info["title"],
                                       info.get("tier_name", ""), info.get("tags", []),
                                       sub.get("language", ""), boj_url)
                api_client.push_file_to_github(github_repo, github_token,
                                               f"{folder}/README.md", readme, msg)
                if api_client.push_file_to_github(github_repo, github_token,
                                                  f"{folder}/{problem_id}{ext}", code, msg):
                    github_pushed += 1
            imported += 1

    return {
        "total_found": len(submissions),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "github_pushed": github_pushed,
        "github_repo": github_repo or "",
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

    # GitHub 설정: 수동 입력 우선, 없으면 저장된 OAuth 설정 사용
    gh_settings = db.get_github_settings()
    github_repo = (req.github_repo or "").strip() or (gh_settings.get("target_repo") if gh_settings else None)
    github_token = (req.github_token or "").strip() or (gh_settings.get("access_token") if gh_settings else None)
    github_push_enabled = bool(github_repo and github_token)
    github_pushed = 0

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
        if github_push_enabled and sub.get("code"):
            ext = api_client._get_file_extension(sub.get("language", ""))
            ref = sub["problem_ref"]
            folder = f"Codeforces/{ref}. {sub['title']}"
            msg = f"[Codeforces] {ref}. {sub['title']}"
            cf_url = sub.get("problem_url", api_client.get_problem_url("codeforces", ref))
            readme = _build_readme("codeforces", ref, sub["title"],
                                   sub.get("tier_name", ""), sub.get("tags", []),
                                   sub.get("language", ""), cf_url)
            api_client.push_file_to_github(github_repo, github_token,
                                           f"{folder}/README.md", readme, msg)
            if api_client.push_file_to_github(github_repo, github_token,
                                              f"{folder}/{ref}{ext}", sub["code"], msg):
                github_pushed += 1

    return {
        "handle": user.get("handle", handle),
        "total_found": len(submissions),
        "imported": len(new_subs),
        "skipped": skipped,
        "has_source": any(bool(s.get("code")) for s in submissions),
        "github_pushed": github_pushed,
        "github_repo": github_repo or "",
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
