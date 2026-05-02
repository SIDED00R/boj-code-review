import db
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/reviews")
def list_reviews(limit: int = 50):
    return {"reviews": db.get_review_history(limit)}


@router.get("/api/reviews/grouped")
def list_reviews_grouped():
    return {"problems": db.get_problems_grouped()}


@router.get("/api/reviews/problem/{platform}/{problem_ref}")
def get_reviews_by_problem(platform: str, problem_ref: str):
    return {"reviews": db.get_reviews_by_problem(platform, problem_ref)}


@router.get("/api/reviews/{review_id}")
def get_review(review_id: int):
    review = db.get_review_detail(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다.")
    return review
