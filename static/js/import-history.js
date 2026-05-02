/* 가져온 기록 목록 표시 — loadImportedHistory와 requestImportedReview만 담당 */

async function loadImportedHistory() {
  const list = document.getElementById('import-history-list');
  if (!list) return;
  try {
    const res = await fetch('/api/solved-history');
    const data = await res.json();
    if (!res.ok || !data.problems || data.problems.length === 0) {
      list.innerHTML = '<div class="alert alert-info" style="margin-top:16px">가져온 기록이 없습니다.</div>';
      return;
    }
    const allProblems = data.problems;
    list.innerHTML = `
      <div class="card" style="margin-top:16px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
          <h3 style="font-size:.95rem;color:var(--text-muted);margin:0;white-space:nowrap">
            가져온 풀이 기록 (<span id="import-count">${allProblems.length}</span>개)
          </h3>
          <input id="import-search" type="text" placeholder="문제번호 또는 제목 검색..."
            style="flex:2;min-width:150px;padding:6px 10px;font-size:.85rem" />
          <select id="import-platform-filter" style="flex:1;min-width:110px;padding:6px 8px;font-size:.85rem">
            <option value="">전체 플랫폼</option>
            <option value="boj">BOJ</option>
            <option value="codeforces">Codeforces</option>
          </select>
          <select id="import-tier-filter" style="flex:1;min-width:110px;padding:6px 8px;font-size:.85rem">
            <option value="">전체 난이도</option>
            <option value="bronze">Bronze</option>
            <option value="silver">Silver</option>
            <option value="gold">Gold</option>
            <option value="platinum">Platinum</option>
            <option value="diamond">Diamond</option>
            <option value="ruby">Ruby</option>
            <option value="unrated">Unrated</option>
          </select>
          <select id="import-per-page" style="min-width:75px;padding:6px 8px;font-size:.85rem">
            <option value="10">10개</option>
            <option value="20" selected>20개</option>
            <option value="50">50개</option>
          </select>
          <select id="import-sort" style="flex:1;min-width:110px;padding:6px 8px;font-size:.85rem">
            <option value="date-desc">최근 가져온 순</option>
            <option value="id-asc">번호 오름차순</option>
            <option value="id-desc">번호 내림차순</option>
            <option value="tier-desc">난이도 높은 순</option>
            <option value="tier-asc">난이도 낮은 순</option>
          </select>
        </div>
        <div id="import-cards"></div>
        <div id="import-pager" style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap;margin-top:12px"></div>
      </div>`;

    const TIER_RANGES = {
      bronze:[1,5], silver:[6,10], gold:[11,15],
      platinum:[16,20], diamond:[21,25], ruby:[26,30], unrated:[0,0],
    };

    let importPage = 1;
    let importPerPage = 20;

    function getFiltered() {
      const q = (document.getElementById('import-search').value || '').trim().toLowerCase();
      const platform = document.getElementById('import-platform-filter').value;
      const tierKey = document.getElementById('import-tier-filter').value;
      const sort = document.getElementById('import-sort').value;

      let result = allProblems.filter(p => {
        if (q && !problemLabel(p).toLowerCase().includes(q) && !p.title.toLowerCase().includes(q)) return false;
        if (platform && (p.platform || 'boj') !== platform) return false;
        if (tierKey) {
          if (tierKey === 'unrated') { if (p.tier !== 0) return false; }
          else { const r = TIER_RANGES[tierKey]; if (p.tier < r[0] || p.tier > r[1]) return false; }
        }
        return true;
      });

      result.sort((a, b) => {
        if (sort === 'id-asc')    return problemLabel(a).localeCompare(problemLabel(b), undefined, { numeric: true });
        if (sort === 'id-desc')   return problemLabel(b).localeCompare(problemLabel(a), undefined, { numeric: true });
        if (sort === 'tier-desc') return b.tier - a.tier;
        if (sort === 'tier-asc')  return a.tier - b.tier;
        return 0;
      });
      return result;
    }

    function renderPagination(totalItems) {
      const totalPages = Math.max(1, Math.ceil(totalItems / importPerPage));
      importPage = Math.min(importPage, totalPages);
      const pager = document.getElementById('import-pager');

      let html = `<button class="page-btn" ${importPage === 1 ? 'disabled' : ''} data-page="${importPage - 1}">‹</button>`;
      let start = Math.max(1, importPage - 3);
      let end = Math.min(totalPages, start + 6);
      if (end - start < 6) start = Math.max(1, end - 6);

      if (start > 1) html += `<button class="page-btn" data-page="1">1</button>${start > 2 ? '<span class="page-ellipsis">…</span>' : ''}`;
      for (let i = start; i <= end; i++) {
        html += `<button class="page-btn ${i === importPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
      }
      if (end < totalPages) html += `${end < totalPages - 1 ? '<span class="page-ellipsis">…</span>' : ''}<button class="page-btn" data-page="${totalPages}">${totalPages}</button>`;
      html += `<button class="page-btn" ${importPage === totalPages ? 'disabled' : ''} data-page="${importPage + 1}">›</button>`;
      pager.innerHTML = html;

      pager.querySelectorAll('.page-btn:not([disabled])').forEach(btn => {
        btn.addEventListener('click', () => {
          importPage = Number(btn.dataset.page);
          renderImportCards(getFiltered());
        });
      });
    }

    function renderImportCards(filtered) {
      const container = document.getElementById('import-cards');
      document.getElementById('import-count').textContent = filtered.length;

      if (!filtered.length) {
        container.innerHTML = '<div style="color:var(--text-muted);font-size:.85rem;padding:8px 0">검색 결과가 없습니다.</div>';
        renderPagination(0);
        return;
      }

      const totalPages = Math.ceil(filtered.length / importPerPage);
      importPage = Math.min(importPage, Math.max(1, totalPages));
      const pageItems = filtered.slice((importPage - 1) * importPerPage, importPage * importPerPage);

      container.innerHTML = pageItems.map(p => {
        const tc = tierClass(p.tier);
        const cardKey = `${p.platform || 'boj'}-${p.problem_ref || p.problem_id}`;
        const platformBadge = (p.platform || 'boj') === 'codeforces' ? 'Codeforces' : 'BOJ';
        const actionBtns = p.has_code
          ? `<button class="btn-sm btn-code btn-view-code" data-platform="${p.platform || 'boj'}" data-problem-ref="${p.problem_ref || p.problem_id}" data-box-key="${cardKey}">코드 보기</button>
             <button class="btn-sm btn-ai btn-review-imported" data-platform="${p.platform || 'boj'}" data-problem-ref="${p.problem_ref || p.problem_id}">AI 리뷰</button>`
          : `<span style="font-size:.75rem;color:var(--text-muted)">코드 없음</span>`;
        return `
          <div class="history-card" data-platform="${p.platform || 'boj'}" data-problem-ref="${p.problem_ref || p.problem_id}">
            <div class="history-card-info">
              <div class="history-card-title">
                <a href="${problemUrl(p)}" target="_blank" style="color:inherit;text-decoration:none">
                  ${problemLabel(p)}. ${p.title}
                </a>
              </div>
              <div class="history-card-meta">${platformBadge}${p.language ? ` · ${p.language}` : ''}</div>
            </div>
            <div class="history-card-right">
              <span class="tier-badge ${tc}" style="font-size:.75rem">${p.tier_name}</span>
              ${actionBtns}
              <span style="font-size:.78rem;color:var(--text-muted)">${p.imported_at.slice(0,10)}</span>
            </div>
          </div>
          <div id="code-view-${cardKey}" class="hidden"></div>`;
      }).join('');

      container.querySelectorAll('.btn-view-code').forEach(btn => {
        btn.addEventListener('click', () => toggleCodeView(btn));
      });
      container.querySelectorAll('.btn-review-imported').forEach(btn => {
        btn.addEventListener('click', () => requestImportedReview(btn));
      });

      renderPagination(filtered.length);
    }

    async function toggleCodeView(btn) {
      const platform = btn.dataset.platform;
      const problemRef = btn.dataset.problemRef;
      const box = document.getElementById(`code-view-${btn.dataset.boxKey}`);
      if (!box.classList.contains('hidden')) {
        box.classList.add('hidden');
        btn.textContent = '코드 보기';
        return;
      }
      btn.textContent = '닫기';
      if (box.dataset.loaded) { box.classList.remove('hidden'); return; }

      box.innerHTML = '<div style="padding:8px;color:var(--text-muted)"><span class="spinner"></span> 불러오는 중...</div>';
      box.classList.remove('hidden');

      try {
        const res = await fetch(`/api/solved-history/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`);
        const data = await res.json();
        const code = data.code || '';
        box.dataset.loaded = '1';
        box.innerHTML = code
          ? `<pre class="code-block" style="margin:0 0 8px">${escapeHtml(code)}</pre>`
          : `<div style="padding:8px;color:var(--text-muted);font-size:.85rem">저장된 코드가 없습니다.</div>`;
      } catch (e) {
        box.innerHTML = `<div style="padding:8px;color:var(--red);font-size:.85rem">불러오기 실패</div>`;
      }
    }

    document.getElementById('import-per-page').addEventListener('change', e => {
      importPerPage = Number(e.target.value);
      importPage = 1;
      renderImportCards(getFiltered());
    });

    renderImportCards(getFiltered());

    ['import-search', 'import-platform-filter', 'import-tier-filter', 'import-sort'].forEach(id => {
      document.getElementById(id).addEventListener('input', () => {
        importPage = 1;
        renderImportCards(getFiltered());
      });
    });

  } catch (e) {
    list.innerHTML = '';
  }
}

async function requestImportedReview(btn) {
  const platform = btn.dataset.platform;
  const problemRef = btn.dataset.problemRef;
  const card = btn.closest('.history-card');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  try {
    const res = await fetch(`/api/review-imported/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '실패');
    card.nextElementSibling?.remove();
    card.remove();
    btn.textContent = '✓ 완료';
  } catch (e) {
    btn.textContent = 'AI 리뷰';
    btn.disabled = false;
    alert('오류: ' + e.message);
  }
}
