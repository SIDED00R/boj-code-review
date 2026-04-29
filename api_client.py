"""
solved.ac API + 백준 페이지 크롤링 모듈
"""
import base64
import re
from functools import lru_cache
import hashlib
import random
import time
from urllib.parse import urlencode
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://solved.ac/",
    "Origin": "https://solved.ac",
}

CODEFORCES_API_BASE = "https://codeforces.com/api"
CODEFORCES_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept-Language": "en-US,en;q=0.9",
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


def get_boj_problem_sections(problem_id: int) -> dict:
    """BOJ 문제 페이지에서 설명/입력/출력 섹션을 각각 반환"""
    url = f"https://www.acmicpc.net/problem/{problem_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        def _text(sel):
            el = soup.select_one(sel)
            return el.get_text(separator="\n", strip=True) if el else ""
        return {
            "description": _text("#problem_description"),
            "input": _text("#problem_input"),
            "output": _text("#problem_output"),
        }
    except Exception:
        return {"description": "", "input": "", "output": ""}


def get_cf_problem_sections(problem_ref: str, translate: bool = False) -> dict:
    """Codeforces 문제 페이지에서 설명/입력/출력 섹션을 XPath로 추출. translate=True일 때만 한국어 번역."""
    try:
        from lxml import etree

        contest_id, index = normalize_codeforces_problem_ref(problem_ref)
        url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        resp = requests.get(url, headers=CODEFORCES_HEADERS, timeout=15)
        resp.raise_for_status()

        tree = etree.fromstring(resp.text.encode(), etree.HTMLParser())
        BASE = '//*[@id="pageContent"]/div[3]/div[2]/div'

        def _xtext(expr: str) -> str:
            nodes = tree.xpath(expr)
            if not nodes:
                return ""
            el = nodes[0]
            for st in el.xpath('.//*[contains(@class,"section-title")]'):
                p = st.getparent()
                if p is not None:
                    p.remove(st)
            return " ".join(el.itertext()).strip()

        raw = {
            "description": _xtext(f'{BASE}/div[2]'),
            "input":       _xtext(f'{BASE}/div[3]'),
            "output":      _xtext(f'{BASE}/div[4]'),
        }

        if not translate:
            return raw

        from openai import OpenAI as _OAI
        import os

        title_nodes = tree.xpath('//div[contains(@class,"title")]')
        title = " ".join(title_nodes[0].itertext()).strip() if title_nodes else problem_ref

        def _translate(text: str) -> str:
            if not text:
                return ""
            try:
                client = _OAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": (
                            "You are a competitive programming translator. "
                            "Translate the given text to natural Korean. "
                            "Keep all mathematical formulas, variable names, numbers, and constraints exactly as written. "
                            "Do NOT add any section headers or labels. "
                            "Return the translated text only."
                        )},
                        {"role": "user", "content": f"Problem: {title}\n\nTranslate:\n\n{text}"},
                    ],
                    max_tokens=2000,
                    temperature=0.3,
                )
                result = res.choices[0].message.content.strip()
                return result if result else text
            except Exception:
                return text

        return {
            "description": _translate(raw["description"]),
            "input":       _translate(raw["input"]),
            "output":      _translate(raw["output"]),
        }
    except Exception:
        return {"description": "", "input": "", "output": ""}


def normalize_codeforces_problem_ref(problem_ref: str) -> tuple[int, str]:
    """
    허용 형식:
    - 4A
    - 4/A
    - 4-A
    - 4 A
    """
    match = re.match(r"^\s*(\d+)\s*[-/_ ]?\s*([A-Za-z][A-Za-z0-9]*)\s*$", problem_ref or "")
    if not match:
        raise ValueError("Codeforces 문제는 '4A' 또는 '4/A' 형식으로 입력해주세요.")
    contest_id = int(match.group(1))
    index = match.group(2).upper()
    return contest_id, index


def get_codeforces_problem_info(problem_ref: str) -> dict:
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    problem = _get_codeforces_problem_lookup().get((contest_id, index))
    if not problem:
        raise ValueError(f"Codeforces 문제를 찾을 수 없습니다: {contest_id}{index}")

    rating = problem.get("rating")
    rating_label = f"Codeforces {rating}" if rating else "Codeforces Unrated"
    return {
        "id": 0,
        "platform": "codeforces",
        "problem_ref": f"{contest_id}{index}",
        "contest_id": contest_id,
        "index": index,
        "title": problem.get("name", f"Problem {contest_id}{index}"),
        "tier": 0,
        "tier_name": rating_label,
        "tags": problem.get("tags", []),
        "url": get_problem_url("codeforces", f"{contest_id}{index}"),
    }


def get_codeforces_problem_statement(problem_ref: str) -> str:
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    urls = [
        f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
        f"https://codeforces.com/contest/{contest_id}/problem/{index}",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=CODEFORCES_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            statement = soup.select_one(".problem-statement")
            if statement:
                return statement.get_text(separator="\n", strip=True)
        except Exception:
            continue

    return "문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 제한적으로 분석합니다."


def get_problem_url(platform: str, problem_ref: str | int) -> str:
    platform = (platform or "boj").lower()
    if platform == "codeforces":
        contest_id, index = normalize_codeforces_problem_ref(str(problem_ref))
        return f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    return f"https://boj.kr/{problem_ref}"


def _codeforces_api_request(method_name: str, params: dict | None = None,
                            api_key: str | None = None, api_secret: str | None = None) -> dict:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    params["lang"] = "en"

    if api_key and api_secret:
        now = int(time.time())
        rand = f"{random.randint(0, 999999):06d}"
        signed_params = {**params, "apiKey": api_key, "time": now}
        sorted_items = sorted((str(k), str(v)) for k, v in signed_params.items())
        query = urlencode(sorted_items)
        sig_base = f"{rand}/{method_name}?{query}#{api_secret}"
        api_sig = rand + hashlib.sha512(sig_base.encode("utf-8")).hexdigest()
        signed_params["apiSig"] = api_sig
        params = signed_params

    resp = requests.get(
        f"{CODEFORCES_API_BASE}/{method_name}",
        params=params,
        headers=CODEFORCES_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "OK":
        raise ValueError(payload.get("comment", "Codeforces API 오류"))
    return payload["result"]


@lru_cache(maxsize=1)
def _get_codeforces_problem_lookup() -> dict[tuple[int, str], dict]:
    lookup = {}
    result = _codeforces_api_request("problemset.problems")
    for problem in result.get("problems", []):
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if contest_id and index:
            lookup[(contest_id, index)] = problem
    return lookup


def get_codeforces_user_info(handle: str) -> dict:
    users = _codeforces_api_request("user.info", {"handles": handle})
    if not users:
        raise ValueError("Codeforces 유저를 찾을 수 없습니다.")
    return users[0]


def get_codeforces_user_submissions(handle: str, count: int = 1000,
                                    api_key: str | None = None,
                                    api_secret: str | None = None) -> list[dict]:
    result = _codeforces_api_request(
        "user.status",
        {"handle": handle, "from": 1, "count": count, "includeSources": "true" if api_key and api_secret else None},
        api_key=api_key,
        api_secret=api_secret,
    )
    submissions = []
    seen = set()
    for sub in result:
        if sub.get("verdict") != "OK":
            continue
        problem = sub.get("problem") or {}
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if not contest_id or not index:
            continue
        problem_ref = f"{contest_id}{index}"
        if problem_ref in seen:
            continue
        seen.add(problem_ref)
        submissions.append({
            "problem_id": 0,
            "problem_ref": problem_ref,
            "contest_id": contest_id,
            "index": index,
            "title": problem.get("name", problem_ref),
            "tier": 0,
            "tier_name": f"Codeforces {problem['rating']}" if problem.get("rating") else "Codeforces Unrated",
            "tags": problem.get("tags", []),
            "language": sub.get("programmingLanguage", ""),
            "code": sub.get("source", "") or "",
            "submission_id": sub.get("id"),
            "problem_url": get_problem_url("codeforces", problem_ref),
        })
    return submissions


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


def search_cf_problems_by_tag(tag: str, min_rating: int, max_rating: int,
                               exclude_refs: set) -> list[dict]:
    """CF API로 태그 + 레이팅 범위로 문제 검색"""
    url = "https://codeforces.com/api/problemset.problems"
    try:
        resp = requests.get(url, params={"tags": tag}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            return []
        problems = data["result"]["problems"]
        stats_map = {
            (s["contestId"], s["index"]): s["solvedCount"]
            for s in data["result"].get("problemStatistics", [])
        }
    except Exception:
        return []

    results = []
    for p in problems:
        rating = p.get("rating", 0)
        if not rating or not (min_rating <= rating <= max_rating):
            continue
        contest_id = p.get("contestId")
        index = p.get("index", "")
        if not contest_id:
            continue
        ref = f"{contest_id}{index}"
        if ref in exclude_refs:
            continue
        results.append({
            "id": ref,
            "title": p.get("name", ref),
            "tier": 0,
            "tier_name": f"CF {rating}",
            "url": f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
            "_solved_count": stats_map.get((contest_id, index), 0),
        })

    results.sort(key=lambda x: -x["_solved_count"])
    for r in results:
        del r["_solved_count"]
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


def exchange_github_code(code: str, client_id: str, client_secret: str) -> str:
    """GitHub OAuth code → access token 교환"""
    resp = requests.post(
        "https://github.com/login/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "code": code},
        headers={"Accept": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token", "")
    if not token:
        raise ValueError(data.get("error_description") or "GitHub 토큰 발급 실패")
    return token


def get_github_user(token: str) -> dict:
    """GitHub 유저 정보 조회"""
    resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_github_user_repos(token: str) -> list[dict]:
    """유저의 GitHub 레포지토리 목록 (최대 100개, 최근 업데이트순)"""
    repos = []
    for page in range(1, 4):
        resp = requests.get(
            "https://api.github.com/user/repos",
            params={"per_page": 100, "page": page, "sort": "updated", "affiliation": "owner"},
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend({"full_name": r["full_name"], "private": r["private"]} for r in batch)
    return repos


def _get_file_extension(language: str) -> str:
    lang = (language or "").lower()
    if "c++" in lang or "c plus" in lang:
        return ".cpp"
    if "python" in lang or "pypy" in lang:
        return ".py"
    if "java" in lang and "javascript" not in lang:
        return ".java"
    if "javascript" in lang or "node" in lang:
        return ".js"
    if "kotlin" in lang:
        return ".kt"
    if "rust" in lang:
        return ".rs"
    if "go" in lang or lang == "go":
        return ".go"
    if "ruby" in lang:
        return ".rb"
    if "c#" in lang or "csharp" in lang:
        return ".cs"
    if lang.startswith("c ") or lang == "c" or "gnu c" in lang and "c++" not in lang:
        return ".c"
    if "php" in lang:
        return ".php"
    if "haskell" in lang:
        return ".hs"
    if "scala" in lang:
        return ".scala"
    if "swift" in lang:
        return ".swift"
    if "typescript" in lang:
        return ".ts"
    if "f#" in lang:
        return ".fs"
    if "d " in lang or lang == "d":
        return ".d"
    return ".txt"


def get_github_file_sha(repo: str, path: str, token: str) -> str | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")
    except Exception:
        return None


def push_file_to_github(
    repo: str, token: str, path: str, content: str, commit_message: str
) -> bool:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    sha = get_github_file_sha(repo, path, token)
    body = {"message": commit_message, "content": encoded}
    if sha:
        body["sha"] = sha
    try:
        resp = requests.put(url, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        return True
    except Exception:
        return False


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
