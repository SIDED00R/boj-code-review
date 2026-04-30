"""
Codeforces 자동 제출 — requests 기반 (브라우저 없음)
Cloudflare가 완화 상태일 때 동작. 차단 시 명확한 에러 반환.
"""
import os
import threading
import requests
from bs4 import BeautifulSoup

_instance: "CFSubmitter | None" = None
_instance_lock = threading.Lock()

CF_LANG_CONTAINS = {
    "python3": "PyPy 3",
    "cpp":     "G++17",
    "java":    "Java 21",
    "rust":    "Rust",
    "go":      "Go ",
    "kotlin":  "Kotlin",
    "js":      "Node.js",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


def get_submitter() -> "CFSubmitter":
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CFSubmitter()
    return _instance


class CFSubmitter:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._logged_in = False
        self._submit_lock = threading.Lock()

    def _is_cf_blocked(self, html: str, status_code: int = 200) -> bool:
        if status_code in (403, 503):
            return True
        low = html.lower()
        return (
            "just a moment" in low
            or "cf-browser-verification" in low
            or "enable javascript" in low
            or "checking your browser" in low
            or "ray id" in low
            or "cloudflare" in low and "challenge" in low
        )

    def _get_csrf(self, html: str) -> str:
        import re
        soup = BeautifulSoup(html, "lxml")
        # meta tag
        meta = soup.find("meta", {"name": "X-Csrf-Token"})
        if meta and meta.get("content"):
            return meta["content"]
        # hidden input
        inp = soup.find("input", {"name": "csrf_token"})
        if inp and inp.get("value"):
            return inp["value"]
        # JS 변수 (window.Codeforces.csrf 또는 var csrf = '...')
        m = re.search(r"csrf[_\-]?[Tt]oken['\"]?\s*[=:]\s*['\"]([a-f0-9]{32,})['\"]", html)
        if m:
            return m.group(1)
        return ""

    def _login(self):
        handle = os.environ.get("CODEFORCES_HANDLE", "")
        password = os.environ.get("CODEFORCES_PASSWORD", "")
        if not handle or not password:
            raise RuntimeError("CODEFORCES_HANDLE과 CODEFORCES_PASSWORD 환경변수를 설정해주세요.")

        resp = self._session.get("https://codeforces.com/enter", timeout=20)
        if self._is_cf_blocked(resp.text, resp.status_code):
            raise RuntimeError(
                "Cloudflare가 접속을 차단했습니다. "
                "Cloud Run의 IP가 봇으로 감지된 것으로 Codeforces 직접 제출이 불가합니다."
            )

        csrf = self._get_csrf(resp.text)
        if not csrf:
            # 응답 앞부분을 에러에 포함해 디버깅
            preview = resp.text[:300].replace("\n", " ")
            raise RuntimeError(f"CSRF 토큰을 가져오지 못했습니다. 응답 미리보기: {preview}")

        resp = self._session.post(
            f"https://codeforces.com/enter?csrf_token={csrf}",
            data={
                "csrf_token": csrf,
                "action": "enter",
                "ftaa": "",
                "bfaa": "",
                "handleOrEmail": handle,
                "password": password,
                "remember": "on",
                "_tta": "",
            },
            timeout=20,
            headers={"Referer": "https://codeforces.com/enter"},
            allow_redirects=True,
        )

        if self._is_cf_blocked(resp.text):
            raise RuntimeError("Cloudflare가 로그인을 차단했습니다.")

        if "logout" not in resp.text.lower():
            raise RuntimeError(
                "CF 로그인 실패. CODEFORCES_HANDLE과 CODEFORCES_PASSWORD를 확인해주세요."
            )

        self._logged_in = True

    def _ensure_logged_in(self):
        if self._logged_in:
            resp = self._session.get("https://codeforces.com", timeout=20)
            if self._is_cf_blocked(resp.text):
                raise RuntimeError("Cloudflare가 접속을 차단했습니다.")
            if "logout" not in resp.text.lower():
                self._logged_in = False

        if not self._logged_in:
            self._login()

    # ── 공개 API ─────────────────────────────────────────────

    def status(self) -> dict:
        try:
            resp = self._session.get("https://codeforces.com", timeout=20)
            cf_blocked = self._is_cf_blocked(resp.text)
            logged_in = "logout" in resp.text.lower()
            return {"browser_open": True, "logged_in": logged_in, "cf_blocked": cf_blocked}
        except Exception as e:
            return {"browser_open": False, "logged_in": False, "cf_blocked": False, "error": str(e)}

    def submit(self, problem_ref: str, code: str, language: str = "python3") -> dict:
        with self._submit_lock:
            try:
                self._ensure_logged_in()

                resp = self._session.get(
                    "https://codeforces.com/problemset/submit", timeout=20
                )
                if self._is_cf_blocked(resp.text, resp.status_code):
                    self._logged_in = False
                    return {"error": "Cloudflare가 제출 페이지를 차단했습니다. 잠시 후 다시 시도해주세요."}

                csrf = self._get_csrf(resp.text)

                # 언어 ID 파싱
                soup = BeautifulSoup(resp.text, "lxml")
                lang_substr = CF_LANG_CONTAINS.get(language.lower(), "PyPy 3")
                program_type_id = "31"  # PyPy 3 기본값
                sel = soup.find("select", {"name": "programTypeId"})
                if sel:
                    for opt in sel.find_all("option"):
                        if lang_substr in opt.text:
                            program_type_id = opt.get("value", "31")
                            break

                resp = self._session.post(
                    f"https://codeforces.com/problemset/submit?csrf_token={csrf}",
                    data={
                        "csrf_token": csrf,
                        "action": "submitSolutionFormSubmit",
                        "submittedProblemCode": problem_ref.upper(),
                        "programTypeId": program_type_id,
                        "tabSize": "4",
                        "source": code,
                        "sourceFile": "",
                    },
                    timeout=30,
                    headers={"Referer": "https://codeforces.com/problemset/submit"},
                    allow_redirects=True,
                )

                if self._is_cf_blocked(resp.text, resp.status_code):
                    self._logged_in = False
                    return {"error": "Cloudflare가 제출을 차단했습니다. 잠시 후 다시 시도해주세요."}

                # 오류 메시지 확인
                soup = BeautifulSoup(resp.text, "lxml")
                err_el = soup.find(class_="error for__source") or soup.find(class_="error")
                if err_el and err_el.text.strip():
                    return {"error": f"CF 오류: {err_el.text.strip()}"}

                handle = os.environ.get("CODEFORCES_HANDLE", "")
                redirect = resp.url if "/submit" not in resp.url else f"https://codeforces.com/submissions/{handle}"

                return {
                    "status": "submitted",
                    "redirect_url": redirect,
                    "problem_ref": problem_ref.upper(),
                }

            except RuntimeError as e:
                return {"error": str(e)}
            except Exception as e:
                return {"error": f"제출 중 오류 발생: {e}"}

    def close(self):
        self._session.close()
        self._logged_in = False
