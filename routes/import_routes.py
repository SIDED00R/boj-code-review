import os
import time
import db
import api_client
from fastapi import APIRouter, HTTPException
from routes.models import ImportRequest, GithubImportRequest, CodeforcesImportRequest
from routes.helpers import build_readme

router = APIRouter()


@router.post("/api/import-github")
def import_from_github(req: GithubImportRequest):
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


@router.post("/api/import")
def import_history(req: ImportRequest):
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
                readme = build_readme("boj", str(problem_id), info["title"],
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


@router.post("/api/import-codeforces")
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
            readme = build_readme("codeforces", ref, sub["title"],
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
