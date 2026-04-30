/* CF 자동 제출 — 브라우저 상태 확인 및 제출 요청만 담당 */

async function submitToCF() {
  if (!_currentProblem?.ref) return;

  const code = window.getEditorValue('pm-code').trim();
  if (!code) {
    showCFSubmitMsg('코드를 먼저 작성해주세요.', 'info');
    return;
  }

  const language = document.getElementById('pm-language').value;
  const btn = document.getElementById('pm-cf-submit-btn');
  const origText = btn.textContent;

  btn.disabled = true;
  btn.textContent = '제출 중...';
  showCFSubmitMsg('<span class="spinner" style="width:14px;height:14px;border-width:2px"></span> Codeforces에 제출 중입니다...', 'info');

  try {
    const res = await fetch('/api/cf-submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        problem_ref: _currentProblem.ref,
        code,
        language,
      }),
    });

    let data;
    try {
      data = await res.json();
    } catch {
      showCFSubmitMsg(`❌ 서버 오류 (${res.status}). 서버 로그를 확인해주세요.`, 'error');
      return;
    }

    if (!res.ok) {
      showCFSubmitMsg(`❌ ${data.detail || '제출 실패'}`, 'error');
    } else {
      const url = data.redirect_url || 'https://codeforces.com/submissions';
      showCFSubmitMsg(
        `✅ 제출 완료! <a href="${escapeHtml(url)}" target="_blank" rel="noopener">제출 현황 보기 →</a>`,
        'success'
      );
    }
  } catch (e) {
    showCFSubmitMsg(`❌ 오류: ${escapeHtml(e.message)}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = origText;
  }
}

function showCFSubmitMsg(html, type) {
  const el = document.getElementById('pm-cf-submit-result');
  if (!el) return;
  const color = type === 'error' ? 'var(--red)' : type === 'success' ? 'var(--green)' : 'var(--text-muted)';
  el.innerHTML = `<div style="font-size:.85rem;color:${color};margin-top:8px">${html}</div>`;
}
