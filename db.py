"""
DB 모듈 - 로컬은 SQLite, 클라우드는 PostgreSQL 자동 선택
DB_TYPE=postgres 환경변수가 있으면 PostgreSQL 사용
"""
import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

USE_POSTGRES = os.environ.get("DB_TYPE", "sqlite").lower() == "postgres"


# ──────────────────────────────────────────────
# 연결
# ──────────────────────────────────────────────

def get_connection():
    if USE_POSTGRES:
        import psycopg2
        unix_socket = os.environ.get("DB_SOCKET")
        if unix_socket:
            return psycopg2.connect(
                dbname=os.environ.get("DB_NAME", "boj_review"),
                user=os.environ.get("DB_USER", "boj_user"),
                password=os.environ.get("DB_PASSWORD", ""),
                host=unix_socket,
            )
        return psycopg2.connect(
            dbname=os.environ.get("DB_NAME", "boj_review"),
            user=os.environ.get("DB_USER", "boj_user"),
            password=os.environ.get("DB_PASSWORD", ""),
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
        )
    else:
        import sqlite3
        db_path = Path(__file__).parent / "coding_recommend.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _ph():
    """플레이스홀더: SQLite는 ?, PostgreSQL은 %s"""
    return "%s" if USE_POSTGRES else "?"


# ──────────────────────────────────────────────
# 초기화
# ──────────────────────────────────────────────

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    if USE_POSTGRES:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id               SERIAL PRIMARY KEY,
                problem_id       INTEGER NOT NULL,
                title            TEXT NOT NULL,
                tier             INTEGER NOT NULL,
                tags             TEXT NOT NULL,
                code             TEXT NOT NULL,
                feedback         TEXT NOT NULL,
                efficiency       TEXT NOT NULL,
                complexity       TEXT NOT NULL DEFAULT '',
                better_algorithm TEXT NOT NULL DEFAULT '',
                strengths        TEXT NOT NULL DEFAULT '[]',
                weaknesses       TEXT NOT NULL DEFAULT '[]',
                created_at       TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tag_stats (
                tag         TEXT PRIMARY KEY,
                good_count  INTEGER NOT NULL DEFAULT 0,
                poor_count  INTEGER NOT NULL DEFAULT 0,
                total_count INTEGER NOT NULL DEFAULT 0
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id       INTEGER NOT NULL,
                title            TEXT NOT NULL,
                tier             INTEGER NOT NULL,
                tags             TEXT NOT NULL,
                code             TEXT NOT NULL,
                feedback         TEXT NOT NULL,
                efficiency       TEXT NOT NULL,
                complexity       TEXT NOT NULL DEFAULT '',
                better_algorithm TEXT NOT NULL DEFAULT '',
                strengths        TEXT NOT NULL DEFAULT '[]',
                weaknesses       TEXT NOT NULL DEFAULT '[]',
                created_at       TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tag_stats (
                tag         TEXT PRIMARY KEY,
                good_count  INTEGER NOT NULL DEFAULT 0,
                poor_count  INTEGER NOT NULL DEFAULT 0,
                total_count INTEGER NOT NULL DEFAULT 0
            )
        """)

    # 기존 테이블에 새 컬럼 추가 (없을 때만)
    new_columns = [
        ("complexity",       "TEXT NOT NULL DEFAULT ''"),
        ("better_algorithm", "TEXT NOT NULL DEFAULT ''"),
        ("strengths",        "TEXT NOT NULL DEFAULT '[]'"),
        ("weaknesses",       "TEXT NOT NULL DEFAULT '[]'"),
    ]
    for col_name, col_def in new_columns:
        try:
            if USE_POSTGRES:
                cur.execute("SAVEPOINT _add_col")
            cur.execute(f"ALTER TABLE reviews ADD COLUMN {col_name} {col_def}")
            if USE_POSTGRES:
                cur.execute("RELEASE SAVEPOINT _add_col")
        except Exception:
            if USE_POSTGRES:
                cur.execute("ROLLBACK TO SAVEPOINT _add_col")
            # SQLite는 예외 무시

    # solved_history 테이블 (가져온 기록 - AI 리뷰 없음)
    if USE_POSTGRES:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS solved_history (
                problem_id   INTEGER PRIMARY KEY,
                title        TEXT NOT NULL,
                tier         INTEGER NOT NULL,
                tags         TEXT NOT NULL DEFAULT '[]',
                code         TEXT NOT NULL DEFAULT '',
                language     TEXT NOT NULL DEFAULT '',
                imported_at  TEXT NOT NULL
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS solved_history (
                problem_id   INTEGER PRIMARY KEY,
                title        TEXT NOT NULL,
                tier         INTEGER NOT NULL,
                tags         TEXT NOT NULL DEFAULT '[]',
                code         TEXT NOT NULL DEFAULT '',
                language     TEXT NOT NULL DEFAULT '',
                imported_at  TEXT NOT NULL
            )
        """)

    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


# ──────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────

def save_review(problem_id: int, title: str, tier: int, tags: list,
                code: str, feedback: str, efficiency: str,
                complexity: str = "", better_algorithm: str = "",
                strengths: list = None, weaknesses: list = None):
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()

    strengths = strengths or []
    weaknesses = weaknesses or []

    # 같은 문제를 이전에 제출한 적 있는지 확인 (태그 통계 중복 방지)
    cur.execute(f"SELECT COUNT(*) FROM reviews WHERE problem_id = {p}", (problem_id,))
    row = cur.fetchone()
    is_first_submission = (row[0] == 0)

    cur.execute(f"""
        INSERT INTO reviews (problem_id, title, tier, tags, code, feedback, efficiency,
                             complexity, better_algorithm, strengths, weaknesses, created_at)
        VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
    """, (problem_id, title, tier, json.dumps(tags, ensure_ascii=False),
          code, feedback, efficiency, complexity, better_algorithm or "",
          json.dumps(strengths, ensure_ascii=False),
          json.dumps(weaknesses, ensure_ascii=False),
          datetime.now().isoformat()))

    # 처음 제출한 문제일 때만 태그 통계 업데이트
    if is_first_submission:
        for tag in tags:
            if USE_POSTGRES:
                cur.execute(f"""
                    INSERT INTO tag_stats (tag, good_count, poor_count, total_count)
                    VALUES ({p}, 0, 0, 0)
                    ON CONFLICT (tag) DO NOTHING
                """, (tag,))
            else:
                cur.execute(f"""
                    INSERT OR IGNORE INTO tag_stats (tag, good_count, poor_count, total_count)
                    VALUES ({p}, 0, 0, 0)
                """, (tag,))

            if efficiency == "good":
                cur.execute(f"""
                    UPDATE tag_stats
                    SET good_count = good_count + 1, total_count = total_count + 1
                    WHERE tag = {p}
                """, (tag,))
            else:
                cur.execute(f"""
                    UPDATE tag_stats
                    SET poor_count = poor_count + 1, total_count = total_count + 1
                    WHERE tag = {p}
                """, (tag,))

    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def _rows_to_dicts(cur, rows):
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]


def get_tag_stats() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tag_stats ORDER BY total_count DESC")
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return rows


def get_weak_tags(top_n: int = 5) -> list:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT tag, poor_count * 1.0 / total_count AS poor_ratio, total_count
        FROM tag_stats
        WHERE total_count >= 1
        ORDER BY poor_ratio DESC, total_count DESC
        LIMIT {p}
    """, (top_n,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return [r["tag"] for r in rows]


def get_average_tier() -> float:
    """
    평균 티어 = 누적 평균의 최댓값 (Unrated 제외)
    중간에 쉬운 문제를 풀어도 내려가지 않고 최고점 유지
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT tier FROM reviews WHERE tier > 0 ORDER BY created_at ASC")
    rows = cur.fetchall()
    if USE_POSTGRES:
        cur.close()
    conn.close()

    if not rows:
        return 10.0

    max_avg = 0.0
    running_sum = 0.0
    for i, row in enumerate(rows, 1):
        tier = row[0] if USE_POSTGRES else row[0]
        running_sum += tier
        running_avg = running_sum / i
        if running_avg > max_avg:
            max_avg = running_avg

    return max_avg


def get_problems_grouped() -> list:
    """문제별로 묶인 리뷰 목록 반환 (최신 제출 기준 정렬)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            problem_id,
            title,
            tier,
            tags,
            COUNT(*) AS submission_count,
            MAX(created_at) AS last_submitted,
            STRING_AGG(efficiency, ',' ORDER BY created_at DESC) AS efficiencies
        FROM reviews
        GROUP BY problem_id, title, tier, tags
        ORDER BY last_submitted DESC
    """ if USE_POSTGRES else """
        SELECT
            problem_id,
            title,
            tier,
            tags,
            COUNT(*) AS submission_count,
            MAX(created_at) AS last_submitted,
            GROUP_CONCAT(efficiency) AS efficiencies
        FROM reviews
        GROUP BY problem_id
        ORDER BY last_submitted DESC
    """)
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        r["tags"] = json.loads(r["tags"])
    return rows


def get_reviews_by_problem(problem_id: int) -> list:
    """특정 문제의 모든 제출 기록 반환"""
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, problem_id, title, tier, tags, code, efficiency, complexity,
               better_algorithm, strengths, weaknesses, feedback, created_at
        FROM reviews WHERE problem_id = {p}
        ORDER BY created_at DESC
    """, (problem_id,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        r["tags"] = json.loads(r["tags"])
        r["strengths"] = json.loads(r.get("strengths") or "[]")
        r["weaknesses"] = json.loads(r.get("weaknesses") or "[]")
    return rows


def get_tier_history() -> list:
    """AI 리뷰 기록의 날짜별 티어 변화 (Unrated 제외)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT problem_id, title, tier, created_at
        FROM reviews
        WHERE tier > 0
        ORDER BY created_at ASC
    """)
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return rows


def get_review_history(limit: int = 10) -> list:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, problem_id, title, tier, tags, efficiency, created_at
        FROM reviews ORDER BY created_at DESC LIMIT {p}
    """, (limit,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        r["tags"] = json.loads(r["tags"])
    return rows


def get_review_detail(review_id: int) -> dict | None:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, problem_id, title, tier, tags, code, feedback, efficiency, created_at
        FROM reviews WHERE id = {p}
    """, (review_id,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    if not rows:
        return None
    r = rows[0]
    r["tags"] = json.loads(r["tags"])
    r["strengths"] = json.loads(r.get("strengths") or "[]")
    r["weaknesses"] = json.loads(r.get("weaknesses") or "[]")
    return r


def save_solved_problem(problem_id: int, title: str, tier: int, tags: list,
                         code: str = "", language: str = ""):
    """풀었던 문제 기록 저장 (리뷰 없음 - 추천 제외용)"""
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    if USE_POSTGRES:
        cur.execute(f"""
            INSERT INTO solved_history (problem_id, title, tier, tags, code, language, imported_at)
            VALUES ({p},{p},{p},{p},{p},{p},{p})
            ON CONFLICT (problem_id) DO NOTHING
        """, (problem_id, title, tier, json.dumps(tags, ensure_ascii=False),
              code, language, datetime.now().isoformat()))
    else:
        cur.execute(f"""
            INSERT OR IGNORE INTO solved_history
                (problem_id, title, tier, tags, code, language, imported_at)
            VALUES ({p},{p},{p},{p},{p},{p},{p})
        """, (problem_id, title, tier, json.dumps(tags, ensure_ascii=False),
              code, language, datetime.now().isoformat()))
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def delete_solved_problem(problem_id: int):
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM solved_history WHERE problem_id = {p}", (problem_id,))
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def clear_solved_history():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM solved_history")
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def get_cached_problem_info(problem_id: int) -> dict | None:
    """
    reviews 또는 solved_history에서 문제 정보 반환 (solved.ac 호출 대체용)
    반환: {title, tier, tier_name, tags} 또는 None
    """
    from api_client import TIER_NAMES
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()

    # reviews 테이블 먼저
    cur.execute(f"SELECT title, tier, tags FROM reviews WHERE problem_id = {p} ORDER BY created_at DESC LIMIT 1", (problem_id,))
    row = cur.fetchone()
    if not row:
        # solved_history 확인
        cur.execute(f"SELECT title, tier, tags FROM solved_history WHERE problem_id = {p}", (problem_id,))
        row = cur.fetchone()

    if USE_POSTGRES:
        cur.close()
    conn.close()

    if not row:
        return None

    title, tier, tags_json = row[0], row[1], row[2]
    tags = json.loads(tags_json) if tags_json else []
    return {
        "id": problem_id,
        "title": title,
        "tier": tier,
        "tier_name": TIER_NAMES.get(tier, "Unrated"),
        "tags": tags,
    }


def get_solved_problem(problem_id: int) -> dict | None:
    """가져온 기록에서 특정 문제 조회"""
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM solved_history WHERE problem_id = {p}", (problem_id,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    if not rows:
        return None
    r = rows[0]
    r["tags"] = json.loads(r["tags"])
    return r


def get_solved_history() -> list:
    """가져온 풀이 기록 목록"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT problem_id, title, tier, language, imported_at,
               CASE WHEN code != '' THEN 1 ELSE 0 END AS has_code
        FROM solved_history ORDER BY imported_at DESC
    """)
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        r["has_code"] = bool(r["has_code"])
    return rows


def get_tag_weakness_data() -> list:
    """
    태그별 취약점 점수 계산용 데이터 반환
    reviews + solved_history 전부 합산
    반환: [{tag, solve_count, last_solved_at, poor_ratio}]
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT tags, created_at FROM reviews")
    review_rows = _rows_to_dicts(cur, cur.fetchall())

    cur.execute("SELECT tags, imported_at FROM solved_history")
    solved_rows = _rows_to_dicts(cur, cur.fetchall())

    cur.execute("SELECT tag, poor_count, total_count FROM tag_stats")
    stat_rows = _rows_to_dicts(cur, cur.fetchall())

    if USE_POSTGRES:
        cur.close()
    conn.close()

    tag_data = {}
    for row in review_rows:
        tags = json.loads(row["tags"])
        date = row.get("created_at", "")
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
            tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    for row in solved_rows:
        tags = json.loads(row["tags"])
        date = row.get("imported_at", "")
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
            tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    poor_map = {}
    for s in stat_rows:
        if s["total_count"] > 0:
            poor_map[s["tag"]] = s["poor_count"] / s["total_count"]

    return [
        {
            "tag": tag,
            "solve_count": data["count"],
            "last_solved_at": data["last_date"],
            "poor_ratio": poor_map.get(tag, 0.0),
        }
        for tag, data in tag_data.items()
    ]


def get_solved_problem_ids() -> set:
    """리뷰한 문제 + 가져온 문제 ID 전부"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT problem_id FROM reviews")
    ids = {r[0] for r in cur.fetchall()}
    try:
        cur.execute("SELECT problem_id FROM solved_history")
        ids |= {r[0] for r in cur.fetchall()}
    except Exception:
        pass
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return ids
