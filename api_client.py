"""
solved.ac API + 백준 페이지 크롤링 모듈
"""
import requests
from bs4 import BeautifulSoup

SOLVED_AC_BASE = "https://solved.ac/api/v3"

TIER_NAMES = {
    0: "Unrated",
    1: "Bronze V", 2: "Bronze IV", 3: "Bronze III", 4: "Bronze II", 5: "Bronze I",
    6: "Silver V", 7: "Silver IV", 8: "Silver III", 9: "Silver II", 10: "Silver I",
    11: "Gold V", 12: "Gold IV", 13: "Gold III", 14: "Gold II", 15: "Gold I",
    16: "Platinum V", 17: "Platinum IV", 18: "Platinum III", 19: "Platinum II", 20: "Platinum I",
    21: "Diamond V", 22: "Diamond IV", 23: "Diamond III", 24: "Diamond II", 25: "Diamond I",
    26: "Ruby V", 27: "Ruby IV", 28: "Ruby III", 29: "Ruby II", 30: "Ruby I",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_problems_bulk(problem_ids: list[int]) -> dict[int, dict]:
    """
    solved.ac /problem/lookup API로 여러 문제 한 번에 조회
    반환: {problem_id: {id, title, tier, tier_name, tags}, ...}
    """
    result = {}
    # 한 번에 최대 100개씩 요청
    for i in range(0, len(problem_ids), 100):
        batch = problem_ids[i:i + 100]
        url = f"{SOLVED_AC_BASE}/problem/lookup"
        try:
            resp = requests.get(
                url,
                params={"problemIds": ",".join(str(p) for p in batch)},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception:
            continue

        for data in items:
            pid = data.get("problemId")
            if not pid:
                continue
            tags = []
            for tag in data.get("tags", []):
                display_names = tag.get("displayNames", [])
                ko = next((d["name"] for d in display_names if d["language"] == "ko"), None)
                en = next((d["name"] for d in display_names if d["language"] == "en"), None)
                name = ko or en or tag.get("key", "")
                if name:
                    tags.append(name)
            tier = data.get("level", 0)
            result[pid] = {
                "id": pid,
                "title": data.get("titleKo") or data.get("title", f"문제 {pid}"),
                "tier": tier,
                "tier_name": TIER_NAMES.get(tier, "Unknown"),
                "tags": tags,
            }
    return result


def get_problem_info(problem_id: int) -> dict:
    """
    solved.ac API로 문제 정보 가져오기
    반환: {id, title, tier, tier_name, tags}
    """
    url = f"{SOLVED_AC_BASE}/problem/show"
    resp = requests.get(url, params={"problemId": problem_id}, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    tags = []
    for tag in data.get("tags", []):
        # 한국어 태그명 우선, 없으면 영어
        display_names = tag.get("displayNames", [])
        ko = next((d["name"] for d in display_names if d["language"] == "ko"), None)
        en = next((d["name"] for d in display_names if d["language"] == "en"), None)
        name = ko or en or tag.get("key", "")
        if name:
            tags.append(name)

    tier = data.get("level", 0)
    return {
        "id": problem_id,
        "title": data.get("titleKo") or data.get("title", f"문제 {problem_id}"),
        "tier": tier,
        "tier_name": TIER_NAMES.get(tier, "Unknown"),
        "tags": tags,
    }


def get_problem_statement(problem_id: int) -> str:
    """
    백준 문제 페이지에서 문제 설명 텍스트 크롤링
    """
    url = f"https://www.acmicpc.net/problem/{problem_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        problem_text = soup.select_one("#problem_description")
        input_text = soup.select_one("#problem_input")
        output_text = soup.select_one("#problem_output")

        parts = []
        if problem_text:
            parts.append("【문제】\n" + problem_text.get_text(separator="\n", strip=True))
        if input_text:
            parts.append("【입력】\n" + input_text.get_text(separator="\n", strip=True))
        if output_text:
            parts.append("【출력】\n" + output_text.get_text(separator="\n", strip=True))

        return "\n\n".join(parts) if parts else "문제 설명을 가져올 수 없습니다."
    except Exception as e:
        return f"크롤링 실패: {e}"


def search_problems_by_tag(tag_key: str, min_tier: int, max_tier: int,
                            exclude_ids: set[int], page: int = 1) -> list[dict]:
    """
    solved.ac API로 태그 + 난이도 범위로 문제 검색
    tag_key: solved.ac 태그 key (영어)
    """
    # solved.ac 검색 쿼리: tag:dp tier:s1..g3 등
    tier_map_inv = _build_tier_key_map()
    min_key = tier_map_inv.get(min_tier, "b1")
    max_key = tier_map_inv.get(max_tier, "p5")

    query = f"tag:{tag_key} tier:{min_key}..{max_key} solved:1000.."
    url = f"{SOLVED_AC_BASE}/search/problem"
    params = {
        "query": query,
        "page": page,
        "sort": "solved",
        "direction": "desc",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
    except Exception:
        return []

    results = []
    for item in items:
        pid = item.get("problemId")
        if pid in exclude_ids:
            continue
        tier = item.get("level", 0)
        results.append({
            "id": pid,
            "title": item.get("titleKo") or item.get("title", f"문제 {pid}"),
            "tier": tier,
            "tier_name": TIER_NAMES.get(tier, "Unknown"),
        })

    return results


def get_tag_key_by_name(tag_name: str) -> str:
    """
    태그 한국어/영어 이름 → solved.ac 태그 key 변환
    solved.ac /tag/list API 사용
    """
    url = f"{SOLVED_AC_BASE}/tag/list"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            display_names = item.get("displayNames", [])
            names = [d["name"].lower() for d in display_names]
            if tag_name.lower() in names or item.get("key", "").lower() == tag_name.lower():
                return item["key"]
    except Exception:
        pass
    # fallback: 이름을 그대로 key로 사용
    return tag_name.lower().replace(" ", "_")


def get_baekjoonhub_problems(repo: str, token: str = None) -> list[dict]:
    """
    BaekjoonHub GitHub 저장소에서 문제 목록 파싱
    repo: "owner/repo" 형식
    반환: [{problem_id, path, sha, language}, ...]
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    # 전체 파일 트리 한 번에 가져오기
    url = f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    tree = resp.json().get("tree", [])
    problems = {}

    BOJ_ROOT_NAMES = {"백준", "boj", "BOJ", "baekjoon", "Baekjoon"}

    for item in tree:
        if item["type"] != "blob":
            continue
        path = item["path"]
        parts = path.split("/")

        # 경로 깊이가 4인 파일만: {root}/{tier}/{problemId. title}/{filename}
        if len(parts) != 4:
            continue

        # 백준 폴더만 처리 (SWEA, 프로그래머스 등 제외)
        if parts[0] not in BOJ_ROOT_NAMES:
            continue

        filename = parts[3]
        if filename == "README.md":
            continue

        # 문제번호 추출: "1000. A+B" → 1000
        folder = parts[2]
        try:
            problem_id = int(folder.split(".")[0].strip())
        except ValueError:
            continue

        if problem_id not in problems:
            problems[problem_id] = {
                "problem_id": problem_id,
                "path": path,
                "sha": item["sha"],
                "language": _ext_to_language(filename),
            }

    return list(problems.values())


def get_raw_github_content(repo: str, path: str, token: str = None) -> str:
    """
    raw.githubusercontent.com으로 파일 내용 가져오기
    - API rate limit 없음 (공개 저장소)
    - 비공개 저장소는 token 필요
    """
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.text


def _ext_to_language(filename: str) -> str:
    ext_map = {
        ".py": "Python 3", ".java": "Java", ".cpp": "C++", ".cc": "C++",
        ".c": "C", ".js": "JavaScript", ".ts": "TypeScript", ".kt": "Kotlin",
        ".rs": "Rust", ".go": "Go", ".rb": "Ruby", ".swift": "Swift",
        ".cs": "C#", ".php": "PHP",
    }
    for ext, lang in ext_map.items():
        if filename.endswith(ext):
            return lang
    return ""


def get_user_submissions(boj_id: str, max_pages: int = 5) -> list[dict]:
    """
    BOJ 맞은 제출 기록 크롤링 (로그인 불필요 - 공개 페이지)
    반환: [{submission_id, problem_id, language}, ...]
    """
    import time
    submissions = []
    seen_ids = set()
    top = None

    for _ in range(max_pages):
        params = {
            "from_mine": "1",
            "user_id": boj_id,
            "result_id": "4",  # Accepted
        }
        if top is not None:
            params["top"] = top

        try:
            resp = requests.get(
                "https://www.acmicpc.net/status",
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        tbody = soup.select_one("table.table-striped tbody")
        if not tbody:
            break

        rows = tbody.select("tr[id^='solution-']")
        if not rows:
            break

        min_id = None
        for row in rows:
            row_id = row.get("id", "")
            try:
                submission_id = int(row_id.replace("solution-", ""))
            except ValueError:
                continue

            # 문제번호는 /problem/ 링크에서 추출
            prob_link = row.select_one("a[href^='/problem/']")
            if not prob_link:
                continue
            try:
                problem_id = int(prob_link.get_text(strip=True))
            except ValueError:
                continue

            # 언어 (8번째 td, 인덱스 6)
            tds = row.select("td")
            language = tds[6].get_text(strip=True) if len(tds) > 6 else ""

            if problem_id not in seen_ids:
                submissions.append({
                    "submission_id": submission_id,
                    "problem_id": problem_id,
                    "language": language,
                })
                seen_ids.add(problem_id)

            if min_id is None or submission_id < min_id:
                min_id = submission_id

        if min_id is None:
            break
        top = min_id - 1
        time.sleep(0.5)  # 서버 부하 방지

    return submissions


def get_submission_code(submission_id: int, session_cookie: str) -> str | None:
    """
    BOJ 제출 코드 가져오기 (로그인 세션 쿠키 필요)
    브라우저 개발자도구 → Application → Cookies → OnlineJudge 값 사용
    """
    url = f"https://www.acmicpc.net/source/{submission_id}"
    # 현재 BOJ는 OnlineJudge 쿠키를 세션으로 사용 (구버전: bojsession)
    cookies = {"OnlineJudge": session_cookie, "bojsession": session_cookie}
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 여러 셀렉터 시도
        for sel in [
            "textarea#code",
            "textarea[name='source']",
            "#source-code pre",
            ".highlight pre",
            "pre.prettyprint",
        ]:
            el = soup.select_one(sel)
            if el:
                return el.get_text()
    except Exception:
        pass
    return None


def _build_tier_key_map() -> dict[int, str]:
    """티어 번호 → solved.ac 검색 tier 코드"""
    codes = [
        "b5","b4","b3","b2","b1",
        "s5","s4","s3","s2","s1",
        "g5","g4","g3","g2","g1",
        "p5","p4","p3","p2","p1",
        "d5","d4","d3","d2","d1",
        "r5","r4","r3","r2","r1",
    ]
    return {i + 1: codes[i] for i in range(len(codes))}
