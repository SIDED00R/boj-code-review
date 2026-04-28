"""
취약점 기반 문제 추천 모듈
점수 = 적게 풀수록(0.5) + AI poor 비율(0.3) + 오래 전에 풀수록(0.2)
"""
from datetime import datetime
from api_client import search_problems_by_tag, search_cf_problems_by_tag, get_tag_key_by_name, TIER_NAMES
import db

# 추천 난이도 범위: 평균 티어 기준 -1 ~ +4 (살짝 어려운 문제 추천)
TIER_RANGE_LOW  = 1
TIER_RANGE_HIGH = 4
# 태그당 최대 추천 문제 수
MAX_PER_TAG = 3


def _score_tags(tag_data: list) -> list:
    """태그별 취약점 점수 계산 후 내림차순 정렬"""
    if not tag_data:
        return []

    now = datetime.now()
    max_count = max(d["solve_count"] for d in tag_data) or 1

    for d in tag_data:
        try:
            last = datetime.fromisoformat(d["last_solved_at"])
            d["days_since"] = (now - last).days
        except Exception:
            d["days_since"] = 365

    max_days = max(d["days_since"] for d in tag_data) or 1

    for d in tag_data:
        count_score   = 1 - (d["solve_count"] / max_count)   # 적게 풀수록 높음
        poor_score    = d["poor_ratio"]                        # AI poor 비율
        recency_score = d["days_since"] / max_days             # 오래됐을수록 높음
        d["weakness_score"] = (
            count_score   * 0.5 +
            poor_score    * 0.3 +
            recency_score * 0.2
        )

    tag_data.sort(key=lambda x: x["weakness_score"], reverse=True)
    return tag_data


def get_weak_tags_scored(top_n: int = 5, platform: str | None = None) -> list[str]:
    tag_data = db.get_tag_weakness_data(platform=platform)
    scored = _score_tags(tag_data)
    return [d["tag"] for d in scored[:top_n]]


def get_recommendations(top_weak_tags: int = 3, platform: str = "boj") -> list[dict]:
    """
    취약 태그 + 현재 수준 기반 문제 추천
    반환: [{"tag": ..., "problems": [{id, title, tier, tier_name, url?}]}]
    """
    if platform == "codeforces":
        return _get_cf_recommendations(top_weak_tags)

    weak_tags = get_weak_tags_scored(top_weak_tags, platform="boj")
    if not weak_tags:
        return []

    avg_tier = db.get_average_tier()
    min_tier = max(1, int(avg_tier) - TIER_RANGE_LOW)
    max_tier = min(30, int(avg_tier) + TIER_RANGE_HIGH)

    solved_ids = db.get_solved_problem_ids()

    recommendations = []
    for tag_name in weak_tags:
        tag_key = get_tag_key_by_name(tag_name)
        problems = search_problems_by_tag(
            tag_key=tag_key,
            min_tier=min_tier,
            max_tier=max_tier,
            exclude_ids=solved_ids,
        )
        problems = problems[:MAX_PER_TAG]

        if problems:
            for p in problems:
                p["url"] = f"https://boj.kr/{p['id']}"
            recommendations.append({
                "tag": tag_name,
                "tag_key": tag_key,
                "problems": problems,
            })

    return recommendations


def _get_cf_recommendations(top_weak_tags: int = 3) -> list[dict]:
    weak_tags = get_weak_tags_scored(top_weak_tags, platform="codeforces")
    if not weak_tags:
        return []

    avg_rating = db.get_average_cf_rating()
    min_rating = max(800, int(avg_rating) - 200)
    max_rating = min(3500, int(avg_rating) + 400)

    exclude_refs = db.get_solved_cf_refs()

    recommendations = []
    for tag in weak_tags:
        problems = search_cf_problems_by_tag(tag, min_rating, max_rating, exclude_refs)
        problems = problems[:MAX_PER_TAG]
        if problems:
            recommendations.append({
                "tag": tag,
                "tag_key": tag,
                "problems": problems,
            })
    return recommendations


def tier_range_description(avg_tier: float) -> str:
    min_tier = max(1, int(avg_tier) - TIER_RANGE_LOW)
    max_tier = min(30, int(avg_tier) + TIER_RANGE_HIGH)
    return f"{TIER_NAMES.get(min_tier, '?')} ~ {TIER_NAMES.get(max_tier, '?')}"
