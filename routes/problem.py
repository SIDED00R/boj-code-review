import os
import asyncio
import re
from fastapi import APIRouter, HTTPException

router = APIRouter()


def _translate_cf_problem(text: str, title: str) -> str:
    try:
        from openai import OpenAI as _OpenAI
        client = _OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "당신은 프로그래밍 문제 번역 전문가입니다. "
                    "Codeforces 문제를 한국어로 번역합니다. "
                    "수식($...$, $$...$$)은 그대로 유지하고, 문제의 의미를 정확하게 전달하세요. "
                    "번역문만 출력하세요."
                )},
                {"role": "user", "content": f"제목: {title}\n\n{text}"},
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[번역 실패: {e}]\n\n{text}"


def _translate_cf_text(text: str, title: str, section_name: str) -> str:
    try:
        from openai import OpenAI as _OpenAI
        client = _OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a competitive programming translator. "
                    "Translate the given text segment from a Codeforces problem into natural Korean. "
                    "IMPORTANT RULES: "
                    "1. Always return the full translated text. Never return empty output. "
                    "2. Keep all mathematical formulas, variable names, numbers, and constraints exactly as written. "
                    "3. Do NOT add any section headers or labels (e.g., do not write '문제:', '입력:', '출력:'). "
                    "4. Translate all English prose naturally to Korean. "
                    "5. If the text is already in Korean or has nothing to translate, return it as-is."
                )},
                {"role": "user", "content": f"Problem: {title}\n\nTranslate this text:\n\n{text}"},
            ],
            max_tokens=2000,
            temperature=0.3,
            timeout=15,
        )
        result = resp.choices[0].message.content.strip()
        return result if result else text
    except Exception:
        return _translate_cf_problem(text, title)


@router.get("/api/problem/cf/{problem_ref}")
async def get_cf_problem(problem_ref: str):
    import requests as _req
    from lxml import etree

    m = re.match(r'^(\d+)([A-Za-z]\d*)$', problem_ref.strip())
    if not m:
        raise HTTPException(400, "잘못된 문제 번호 형식 (예: 4A, 1234B)")
    contest_id, index = m.group(1), m.group(2).upper()

    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    try:
        resp = _req.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(502, f"CF 페이지 로딩 실패: {e}")

    tree = etree.fromstring(resp.text.encode(), etree.HTMLParser())

    def _xpath_text(expr: str) -> str:
        nodes = tree.xpath(expr)
        if not nodes:
            return ""
        el = nodes[0]
        for st in el.xpath('.//*[contains(@class,"section-title")]'):
            parent = st.getparent()
            if parent is not None:
                parent.remove(st)
        return " ".join(el.itertext()).strip()

    def _limit_value(xpath_expr: str) -> str:
        nodes = tree.xpath(xpath_expr)
        if not nodes:
            return ""
        el = nodes[0]
        prop_nodes = el.xpath('.//*[contains(@class,"property-title")]')
        prop_text = " ".join(prop_nodes[0].itertext()).strip() if prop_nodes else ""
        full_text = " ".join(el.itertext()).strip()
        return full_text.replace(prop_text, "", 1).strip()

    title = _xpath_text('//div[contains(@class,"title")]') or f"CF {problem_ref}"
    time_limit   = _limit_value('//div[contains(@class,"time-limit")]')
    memory_limit = _limit_value('//div[contains(@class,"memory-limit")]')

    BASE = '//*[@id="pageContent"]/div[3]/div[2]/div'
    statement_text = _xpath_text(f'{BASE}/div[2]')
    input_text     = _xpath_text(f'{BASE}/div[3]')
    output_text    = _xpath_text(f'{BASE}/div[4]')

    note_nodes = tree.xpath('//*[contains(@class,"note")]')
    note_text = " ".join(note_nodes[0].itertext()).strip() if note_nodes else ""

    samples = []
    sample_container = tree.xpath(f'{BASE}/div[5]')
    if sample_container:
        sc = sample_container[0]
        inp_pres = sc.xpath('.//div[contains(@class,"input")]//pre')
        out_pres = sc.xpath('.//div[contains(@class,"output")]//pre')
        for inp_pre, out_pre in zip(inp_pres, out_pres):
            samples.append({
                "input":  "\n".join(inp_pre.itertext()).strip(),
                "output": "\n".join(out_pre.itertext()).strip(),
            })

    async def _translate_async(text, section):
        if not text:
            return ""
        return await asyncio.to_thread(_translate_cf_text, text, title, section)

    statement_ko, input_ko, output_ko, note_ko = await asyncio.gather(
        _translate_async(statement_text, "statement"),
        _translate_async(input_text,     "input"),
        _translate_async(output_text,    "output"),
        _translate_async(note_text,      "note"),
    )

    return {
        "title": title,
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "statement_sections_ko": {
            "statement": statement_ko,
            "input":     input_ko,
            "output":    output_ko,
            "note":      note_ko,
        },
        "samples": samples,
        "url": url,
        "contest_id": contest_id,
        "index": index,
    }
