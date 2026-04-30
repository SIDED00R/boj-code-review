"""
Codeforces 제출 라우트
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import cf_submitter

router = APIRouter()


class SubmitRequest(BaseModel):
    problem_ref: str
    code: str
    language: str = "python3"


@router.get("/api/cf-submit/status")
def browser_status():
    submitter = cf_submitter.get_submitter()
    return submitter.status()


@router.post("/api/cf-submit")
def submit(req: SubmitRequest):
    if not req.problem_ref.strip() or not req.code.strip():
        raise HTTPException(400, "problem_ref와 code는 필수입니다.")

    try:
        submitter = cf_submitter.get_submitter()
        result = submitter.submit(req.problem_ref.strip(), req.code, req.language)
    except Exception as e:
        raise HTTPException(500, f"제출 처리 중 예외 발생: {e}")

    if "error" in result:
        raise HTTPException(400, result["error"])

    return result
