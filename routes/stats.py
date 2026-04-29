import os
import db
import api_client
import analyzer
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/tier-history")
def get_tier_history():
    return {"history": db.get_tier_history()}


@router.get("/api/stats")
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
