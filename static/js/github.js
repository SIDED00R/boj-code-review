/* GitHub OAuth 연결 UI — GitHub 인증 상태 표시 및 연결/해제만 담당 */

async function loadGithubStatus() {
  try {
    const res = await fetch('/auth/github/status');
    const data = await res.json();
    const connectBtn = document.getElementById('github-connect-btn');
    const statusBadge = document.getElementById('github-status-badge');
    const usernameBadge = document.getElementById('github-username-badge');
    const repoSelect = document.getElementById('github-repo-select');

    if (data.connected) {
      connectBtn.style.display = 'none';
      statusBadge.style.display = 'flex';
      usernameBadge.textContent = `@${data.username}`;

      try {
        const repoRes = await fetch('/auth/github/repos');
        const repoData = await repoRes.json();
        repoSelect.innerHTML = '<option value="">저장소 선택...</option>' +
          (repoData.repos || []).map(r =>
            `<option value="${r.full_name}" ${r.full_name === data.target_repo ? 'selected' : ''}>${r.full_name}${r.private ? ' 🔒' : ''}</option>`
          ).join('');
      } catch {}

      repoSelect.addEventListener('change', async () => {
        const repo = repoSelect.value;
        if (!repo) return;
        await fetch('/auth/github/repo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo }),
        });
      });
    } else {
      connectBtn.style.display = '';
      statusBadge.style.display = 'none';
    }
  } catch {}
}

document.getElementById('github-connect-btn')?.addEventListener('click', () => {
  window.location.href = '/auth/github';
});

document.getElementById('github-disconnect-btn')?.addEventListener('click', async () => {
  if (!confirm('GitHub 연결을 해제하시겠습니까?')) return;
  await fetch('/auth/github', { method: 'DELETE' });
  location.reload();
});

(function () {
  const params = new URLSearchParams(location.search);
  if (params.get('github') === 'connected') {
    history.replaceState({}, '', '/');
  } else if (params.get('github') === 'error') {
    alert('GitHub 연결에 실패했습니다. 다시 시도해주세요.');
    history.replaceState({}, '', '/');
  }
})();

loadGithubStatus();
