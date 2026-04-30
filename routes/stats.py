import os
import db
import api_client
import analyzer
from fastapi import APIRouter, HTTPException
from typing import Optional

router = APIRouter()


@router.get("/api/tier-history")
def get_tier_history():
    return {"history": db.get_tier_history()}


@router.get("/api/stats")
def get_stats(platform: Optional[str] = "boj"):
    history = db.get_review_history(20)
    total_reviews = db.get_total_review_count(platform)

    if platform == "codeforces":
        avg_rating = db.get_average_cf_rating()
        tag_stats = db.get_cf_tag_stats()
        return {
            "platform": "codeforces",
            "avg_rating": avg_rating,
            "avg_tier_name": f"CF {int(avg_rating)}",
            "total_reviews": total_reviews,
            "tag_stats": tag_stats,
            "history": [r for r in history if r.get("platform") == "codeforces"],
        }

    avg_tier = db.get_average_tier()
    tag_stats = db.get_tag_stats()
    return {
        "platform": "boj",
        "avg_tier": avg_tier,
        "avg_tier_name": api_client.TIER_NAMES.get(int(avg_tier), "N/A"),
        "total_reviews": total_reviews,
        "tag_stats": tag_stats,
        "history": [r for r in history if r.get("platform", "boj") == "boj"],
    }


@router.get("/api/report")
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
