import os
import db
import api_client
import analyzer
from fastapi import APIRouter, HTTPException
from routes.models import ReviewRequest, PushReviewRequest, ReviewResponse
from routes.helpers import build_readme

router = APIRouter()


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


@router.post("/api/review", response_model=ReviewResponse)
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


@router.post("/api/push-review")
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
        if not req.description:
            sections = api_client.get_boj_problem_sections(int(req.problem_ref))
            description = sections.get("description", "")
            input_desc  = sections.get("input", "")
            output_desc = sections.get("output", "")
        else:
            description, input_desc, output_desc = req.description, req.input_desc, req.output_desc
    else:
        folder = f"Codeforces/{req.problem_ref}. {req.title}"
        msg = f"[Codeforces] {req.problem_ref}. {req.title}"
        if not req.description:
            sections = api_client.get_cf_problem_sections(req.problem_ref, translate=False)
            description = sections.get("description", "")
            input_desc  = sections.get("input", "")
            output_desc = sections.get("output", "")
        else:
            description, input_desc, output_desc = req.description, req.input_desc, req.output_desc

    readme = build_readme(req.platform, req.problem_ref, req.title,
                          req.tier_name, req.tags, req.language, url,
                          description, input_desc, output_desc)
    api_client.push_file_to_github(github_repo, github_token, f"{folder}/README.md", readme, msg)
    ok = api_client.push_file_to_github(github_repo, github_token,
                                        f"{folder}/{req.problem_ref}{ext}", req.code, msg)
    if not ok:
        raise HTTPException(status_code=500, detail="GitHub push에 실패했습니다.")
    return {"pushed": True, "repo": github_repo, "path": folder}
