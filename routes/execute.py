import os
import time
import subprocess
import tempfile
from fastapi import APIRouter, HTTPException
from routes.models import ExecuteRequest

router = APIRouter()

# 코드 실행 subprocess에 전달할 안전한 환경변수만 허용 (API 키 등 민감 정보 차단)
_SAFE_ENV_KEYS = {"PATH", "HOME", "TEMP", "TMP", "TMPDIR", "SYSTEMROOT", "SYSTEMDRIVE", "LANG", "LC_ALL"}
_BASE_ENV = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
_COMPILE_TIMEOUT = int(os.environ.get("COMPILE_TIMEOUT", "30"))


def _run_python(code: str, stdin: str, timeout: int) -> dict:
    env = {**_BASE_ENV, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        r = subprocess.run(
            ["python3", "-c", code],
            input=stdin, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": "[Python3를 찾을 수 없습니다]", "exit_code": -1}


def _run_cpp(code: str, stdin: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "sol.cpp")
        exe = os.path.join(tmpdir, "sol")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            cr = subprocess.run(
                ["g++", "-O2", "-std=c++17", "-o", exe, src],
                capture_output=True, text=True, timeout=_COMPILE_TIMEOUT, env=_BASE_ENV,
            )
        except FileNotFoundError:
            return {"stdout": "", "stderr": "[g++를 찾을 수 없습니다]", "exit_code": -1}
        if cr.returncode != 0:
            return {"stdout": "", "stderr": cr.stderr, "exit_code": cr.returncode}
        try:
            rr = subprocess.run(
                [exe], input=stdin, capture_output=True, text=True,
                timeout=timeout, env=_BASE_ENV,
            )
            return {"stdout": rr.stdout, "stderr": rr.stderr, "exit_code": rr.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}


@router.post("/api/execute")
def execute_code(req: ExecuteRequest):
    t0 = time.time()
    lang = req.language.lower()
    if "python" in lang or "pypy" in lang:
        result = _run_python(req.code, req.stdin, req.timeout_sec)
    elif "c++" in lang or "cpp" in lang or "gnu" in lang:
        result = _run_cpp(req.code, req.stdin, req.timeout_sec)
    else:
        raise HTTPException(400, f"지원하지 않는 언어: {req.language}")
    result["time_ms"] = int((time.time() - t0) * 1000)
    return result
