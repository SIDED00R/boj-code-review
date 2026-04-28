/* ── GitHub OAuth 연결 ── */
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

      // 레포지토리 목록 로드
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

// URL 파라미터로 OAuth 결과 감지
(function() {
  const params = new URLSearchParams(location.search);
  if (params.get('github') === 'connected') {
    history.replaceState({}, '', '/');
  } else if (params.get('github') === 'error') {
    alert('GitHub 연결에 실패했습니다. 다시 시도해주세요.');
    history.replaceState({}, '', '/');
  }
})();

loadGithubStatus();

/* ── 테마 토글 ── */
const themeBtn = document.getElementById('theme-toggle');
const savedTheme = localStorage.getItem('theme') || 'dark';
if (savedTheme === 'light') {
  document.body.classList.add('light');
  themeBtn.textContent = '☀️';
}
themeBtn.addEventListener('click', () => {
  const isLight = document.body.classList.toggle('light');
  themeBtn.textContent = isLight ? '☀️' : '🌙';
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
});

/* ── 탭 전환 ── */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => {
      s.classList.remove('active');
      s.classList.add('hidden');
    });
    btn.classList.add('active');
    const tab = document.getElementById(`tab-${btn.dataset.tab}`);
    tab.classList.remove('hidden');
    tab.classList.add('active');
    // 탭 클릭 시 자동 로드
    if (btn.dataset.tab === 'history') loadHistory();
    if (btn.dataset.tab === 'import') loadImportedHistory();
    if (btn.dataset.tab === 'stats') loadTierChart();
  });
});

/* ── 티어 변화 그래프 ── */
const TIER_LABELS = {
  0:'Unrated',1:'Bronze V',2:'Bronze IV',3:'Bronze III',4:'Bronze II',5:'Bronze I',
  6:'Silver V',7:'Silver IV',8:'Silver III',9:'Silver II',10:'Silver I',
  11:'Gold V',12:'Gold IV',13:'Gold III',14:'Gold II',15:'Gold I',
  16:'Platinum V',17:'Platinum IV',18:'Platinum III',19:'Platinum II',20:'Platinum I',
  21:'Diamond V',22:'Diamond IV',23:'Diamond III',24:'Diamond II',25:'Diamond I',
  26:'Ruby V',27:'Ruby IV',28:'Ruby III',29:'Ruby II',30:'Ruby I',
};
const TIER_COLORS = t =>
  t <= 5  ? '#cd7f32' :
  t <= 10 ? '#c0c0c0' :
  t <= 15 ? '#ffd700' :
  t <= 20 ? '#4fc3f7' :
  t <= 25 ? '#b39ddb' :
            '#ef5350';

let tierChartInstance = null;

async function loadTierChart() {
  if (tierChartInstance) {
    tierChartInstance.destroy();
    tierChartInstance = null;
  }
  try {
    const res = await fetch('/api/tier-history');
    const data = await res.json();
    const history = data.history || [];

    if (!history.length) {
      document.getElementById('tier-chart').classList.add('hidden');
      document.getElementById('tier-chart-empty').classList.remove('hidden');
      return;
    }

    document.getElementById('tier-chart').classList.remove('hidden');
    document.getElementById('tier-chart-empty').classList.add('hidden');

    // 문제별 최신 리뷰 1개만 남기기 (이미 created_at DESC로 정렬되어 있으므로 역순 처리)
    const seenPids = new Set();
    const deduped = [];
    [...history].reverse().forEach(r => {
      if (!seenPids.has(r.problem_id)) {
        seenPids.add(r.problem_id);
        deduped.push(r);
      }
    });
    deduped.sort((a, b) => a.created_at.localeCompare(b.created_at));

    // 날짜별 그룹핑 (툴팁용, deduped 기준)
    const byDate = {};
    deduped.forEach(r => {
      const d = r.created_at.slice(0, 10);
      if (!byDate[d]) byDate[d] = [];
      byDate[d].push(r);
    });

    // 내 티어: 누적 평균의 최댓값 (절대 내려가지 않음) - 날짜별 1포인트
    const uniqueDates = Object.keys(byDate).sort();
    let runningSum = 0, runningCount = 0, maxAvg = 0;
    const myTierLine = [];
    for (const d of uniqueDates) {
      for (const r of byDate[d]) {
        runningSum += r.tier;
        runningCount++;
        const avg = runningSum / runningCount;
        if (avg > maxAvg) maxAvg = avg;
      }
      myTierLine.push({ x: d, y: maxAvg });
    }

    const isDark = !document.body.classList.contains('light');
    const gridColor = isDark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)';
    const textColor = isDark ? '#8892a4' : '#5a6282';

    const ctx = document.getElementById('tier-chart').getContext('2d');
    tierChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [
          {
            label: '내 티어',
            data: myTierLine,
            borderColor: '#4ecca3',
            backgroundColor: 'rgba(78,204,163,0.08)',
            borderWidth: 2.5,
            pointRadius: 3,
            pointHoverRadius: 5,
            fill: true,
            stepped: 'after',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: textColor, font: { size: 12 } } },
          tooltip: {
            callbacks: {
              label: ctx => `내 티어: ${TIER_LABELS[Math.round(ctx.parsed.y)] || ctx.parsed.y.toFixed(1)}`,
            },
          },
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'day', displayFormats: { day: 'MM/dd' } },
            ticks: { color: textColor, maxTicksLimit: 10, maxRotation: 0 },
            grid: { color: gridColor },
          },
          y: {
            min: 0, max: 30,
            ticks: {
              color: textColor,
              stepSize: 5,
              callback: v => ({ 0:'Unrated',5:'Bronze I',10:'Silver I',15:'Gold I',20:'Platinum I',25:'Diamond I',30:'Ruby I' })[v] || '',
            },
            grid: { color: gridColor },
          },
        },
      },
    });
  } catch (e) {
    console.error('tier chart error', e);
  }
}

/* ── 유틸 ── */
function tierClass(tier) {
  if (tier === 0) return '';
  if (tier <= 5) return 'tier-bronze';
  if (tier <= 10) return 'tier-silver';
  if (tier <= 15) return 'tier-gold';
  if (tier <= 20) return 'tier-platinum';
  if (tier <= 25) return 'tier-diamond';
  return 'tier-ruby';
}

function effClass(e) {
  return { good: 'eff-good', ok: 'eff-ok', poor: 'eff-poor' }[e] || '';
}

function effLabel(e) {
  return { good: '● 효율적', ok: '◐ 보통', poor: '● 비효율적' }[e] || e;
}

function problemLabel(problem) {
  if (problem.platform === 'codeforces') return problem.problem_ref;
  return String(problem.problem_id ?? problem.problem_ref ?? '');
}

function problemUrl(problem) {
  if (problem.problem_url) return problem.problem_url;
  if (problem.platform === 'codeforces') {
    const ref = String(problem.problem_ref || '').replace(/[^0-9A-Za-z]/g, '');
    const match = ref.match(/^(\d+)([A-Za-z][A-Za-z0-9]*)$/);
    if (match) return `https://codeforces.com/problemset/problem/${match[1]}/${match[2].toUpperCase()}`;
  }
  return `https://boj.kr/${problem.problem_id ?? problem.problem_ref}`;
}

function encodedProblemPath(problem) {
  return `/api/reviews/problem/${encodeURIComponent(problem.platform || 'boj')}/${encodeURIComponent(problem.problem_ref || String(problem.problem_id || ''))}`;
}

const platformSelect = document.getElementById('problem-platform');
const problemIdInput = document.getElementById('problem-id');
const problemIdLabel = document.getElementById('problem-id-label');
const problemIdHelp = document.getElementById('problem-id-help');

function syncProblemInputUI() {
  const platform = platformSelect?.value || 'boj';
  if (platform === 'codeforces') {
    problemIdLabel.textContent = '문제 번호';
    problemIdInput.placeholder = '예) 4A 또는 4/A';
    problemIdHelp.textContent = 'Codeforces: contestId + index 형식으로 입력하세요. 예) 4A, 4/A';
  } else {
    problemIdLabel.textContent = '문제 번호';
    problemIdInput.placeholder = '예) 1000';
    problemIdHelp.textContent = '백준: 숫자만 입력하세요. 예) 1000';
  }
}

platformSelect?.addEventListener('change', syncProblemInputUI);
syncProblemInputUI();

function setLoading(btn, loading) {
  btn.disabled = loading;
  btn.innerHTML = loading
    ? '<span class="spinner"></span> 분석 중...'
    : btn.dataset.label;
}

function showError(container, msg) {
  container.innerHTML = `<div class="alert alert-error">❌ ${msg}</div>`;
  container.classList.remove('hidden');
}

/* ── 코드 리뷰 ── */
const reviewBtn = document.getElementById('review-btn');
reviewBtn.dataset.label = '분석 시작';

reviewBtn.addEventListener('click', async () => {
  const platform = platformSelect?.value || 'boj';
  const problemId = document.getElementById('problem-id').value.trim();
  const problemStatement = document.getElementById('problem-statement').value.trim();
  const code = document.getElementById('code-input').value.trim();
  const result = document.getElementById('review-result');

  if (!problemId) { showError(result, '문제 번호를 입력하세요.'); return; }
  if (!code)      { showError(result, '코드를 입력하세요.'); return; }

  setLoading(reviewBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 코드를 분석 중입니다... (10~20초 소요)</div>';
  result.classList.remove('hidden');

  try {
    const payload = { platform, code, problem_statement: problemStatement || null };
    if (platform === 'codeforces') payload.problem_ref = problemId;
    else payload.problem_id = Number(problemId);

    const res = await fetch('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '분석 실패');
    renderReview(result, data);
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(reviewBtn, false);
  }
});

function detectLanguage(code) {
  // C++ (가장 흔함 — 넓게 잡음)
  if (/#include/.test(code) || /\bstd::/.test(code) || /\bcout\b/.test(code) ||
      /\bcin\b/.test(code) || /\bint\s+main\s*\(/.test(code) || /\bvector\s*</.test(code) ||
      /\busing\s+namespace\s+std/.test(code)) return 'GNU C++17';
  // Python
  if (/\bdef\s+\w/.test(code) || /\bimport\s+\w/.test(code) ||
      /\bprint\s*\(/.test(code) || /\binput\s*\(/.test(code) ||
      /\brange\s*\(/.test(code)) return 'Python 3';
  // Java
  if (/\bpublic\s+class\b/.test(code) || /\bSystem\.out\b/.test(code) ||
      /\bScanner\b/.test(code) || /\bBufferedReader\b/.test(code)) return 'Java';
  // Kotlin
  if (/\bfun\s+main\b/.test(code) || /\bprintln\b/.test(code) ||
      /\breadLine\b/.test(code)) return 'Kotlin';
  // C#
  if (/\busing\s+System\b/.test(code) || /\bConsole\.\w/.test(code)) return 'C#';
  // Rust
  if (/\bfn\s+main\s*\(/.test(code) || /\buse\s+std::io/.test(code) ||
      /\blet\s+mut\b/.test(code)) return 'Rust';
  // Go
  if (/\bpackage\s+main\b/.test(code) || /\bfmt\./.test(code)) return 'Go';
  // JavaScript / Node
  if (/\brequire\s*\(/.test(code) || /\bconsole\.log\b/.test(code)) return 'JavaScript';
  // C (fallback — #include없이 printf/scanf만 있는 경우)
  if (/\bprintf\s*\(/.test(code) || /\bscanf\s*\(/.test(code)) return 'C';
  return '';
}

function renderReview(container, d) {
  const tc = tierClass(d.tier);
  const tagsHtml = d.tags.map(t => `<span class="tag">${t}</span>`).join('');
  const strengthsHtml = (d.strengths || []).map(s => `<li>${s}</li>`).join('') || '<li>-</li>';
  const weaknessesHtml = (d.weaknesses || []).map(w => `<li>${w}</li>`).join('') || '<li>-</li>';
  const feedbackHtml = marked.parse(d.feedback || '');
  const label = problemLabel(d);
  const betterAlgo = d.better_algorithm
    ? `<div class="summary-item"><div class="summary-label">더 나은 알고리즘</div><div class="summary-value" style="font-size:.85rem;color:var(--yellow)">${d.better_algorithm}</div></div>`
    : '';

  container.innerHTML = `
    <div class="result-card">
      <div class="problem-header">
        <span class="problem-title">
          <a href="${problemUrl(d)}" target="_blank" style="color:inherit;text-decoration:none">
            ${label}. ${d.title}
          </a>
        </span>
        <span class="tier-badge ${tc}">${d.tier_name}</span>
      </div>

      <div class="tag-list">${tagsHtml || '<span class="tag">태그 없음</span>'}</div>

      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">효율성 평가</div>
          <div class="summary-value ${effClass(d.efficiency)}">${effLabel(d.efficiency)}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">시간복잡도</div>
          <div class="summary-value">${d.complexity}</div>
        </div>
        ${betterAlgo}
      </div>

      <div class="points-grid">
        <div class="points-box good">
          <h4>✓ 잘한 점</h4>
          <ul>${strengthsHtml}</ul>
        </div>
        <div class="points-box bad">
          <h4>✗ 개선할 점</h4>
          <ul>${weaknessesHtml}</ul>
        </div>
      </div>

      <div class="feedback-box">
        <h4>상세 피드백</h4>
        <div class="markdown-body">${feedbackHtml}</div>
      </div>

      <div style="margin-top:16px;display:flex;align-items:center;gap:10px">
        <button id="push-github-btn" class="btn-primary" style="font-size:.85rem;padding:7px 16px">
          🐙 GitHub에 올리기
        </button>
        <span id="push-github-msg" style="font-size:.82rem"></span>
      </div>
    </div>
  `;

  document.getElementById('push-github-btn').addEventListener('click', async () => {
    const btn = document.getElementById('push-github-btn');
    const msg = document.getElementById('push-github-msg');
    const code = document.getElementById('code-input').value.trim();
    const langSelect = document.getElementById('code-language');
    const language = (langSelect && langSelect.value) || detectLanguage(code);
    btn.disabled = true;
    btn.textContent = '올리는 중...';
    msg.textContent = '';
    try {
      const res = await fetch('/api/push-review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: d.platform,
          problem_ref: d.problem_ref,
          title: d.title,
          tier_name: d.tier_name,
          tags: d.tags,
          code,
          language,
          url: d.problem_url,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'push 실패');
      btn.textContent = '✓ 완료';
      msg.innerHTML = `<span style="color:var(--green)">🐙 <b>${data.repo}</b>에 push 완료</span>`;
    } catch (e) {
      btn.textContent = '🐙 GitHub에 올리기';
      btn.disabled = false;
      msg.innerHTML = `<span style="color:var(--red)">${e.message}</span>`;
    }
  });
}

/* ── 문제 추천 ── */
const recommendBtn = document.getElementById('recommend-btn');
recommendBtn.dataset.label = '추천받기';

recommendBtn.addEventListener('click', async () => {
  const result = document.getElementById('recommend-result');
  setLoading(recommendBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 추천 문제를 검색 중입니다...</div>';

  try {
    const platform = document.getElementById('recommend-platform')?.value || 'codeforces';
    const res = await fetch(`/api/recommend?platform=${encodeURIComponent(platform)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '추천 실패');
    renderRecommend(result, data);
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(recommendBtn, false);
  }
});

function renderRecommend(container, data) {
  if (!data.recommendations || data.recommendations.length === 0) {
    container.innerHTML = `
      <div class="alert alert-info">
        아직 추천 데이터가 없습니다. 먼저 코드 리뷰를 몇 개 진행해보세요.
      </div>`;
    return;
  }

  const tc = tierClass(Math.floor(data.avg_tier));
  let html = `
    <div class="result-card">
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">현재 평균 레벨 <span style="font-size:.75rem;color:var(--text-muted)">(최근 30개)</span></div>
          <div class="summary-value"><span class="tier-badge ${tc}">${data.tier_name}</span></div>
        </div>
        <div class="summary-item">
          <div class="summary-label">추천 난이도 범위</div>
          <div class="summary-value" style="font-size:.9rem">${data.tier_range || '-'}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">취약 태그</div>
          <div class="summary-value" style="font-size:.82rem">${(data.weak_tags || []).join(', ')}</div>
        </div>
      </div>
  `;

  for (const rec of data.recommendations) {
    html += `<div class="rec-tag-title">📌 ${rec.tag}</div><div class="rec-problems">`;
    for (const p of rec.problems) {
      const ptc = tierClass(p.tier);
      const isCF = p.url && p.url.includes('codeforces');
      if (isCF) {
        const safeTitle = p.title.replace(/'/g, "\\'");
        const safeTier = p.tier_name.replace(/'/g, "\\'");
        html += `
          <div class="rec-problem-card cf-clickable" onclick="openProblemModal('${p.id}', '${safeTitle}', '${safeTier}')">
            <span>${p.id}. ${p.title}</span>
            <span class="tier-badge ${ptc}">${p.tier_name}</span>
          </div>`;
      } else {
        html += `
          <div class="rec-problem-card">
            <a href="${p.url || 'https://boj.kr/' + p.id}" target="_blank">${p.id}. ${p.title}</a>
            <span class="tier-badge ${ptc}">${p.tier_name}</span>
          </div>`;
      }
    }
    html += `</div>`;
  }
  html += `</div>`;
  container.innerHTML = html;
}

/* ── 문제 풀기 모달 ── */
let _currentProblem = null;

function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function openProblemModal(ref, title, tierName) {
  _currentProblem = { ref, title, tierName, samples: [] };

  const modal = document.getElementById('problem-modal');
  modal.classList.remove('hidden');
  document.getElementById('pm-title').textContent = title;
  document.getElementById('pm-difficulty').textContent = tierName;
  document.getElementById('pm-meta').textContent = '';
  document.getElementById('pm-loading').classList.remove('hidden');
  document.getElementById('pm-loading').innerHTML = '<span class="spinner"></span> 문제 불러오는 중...';
  document.getElementById('pm-statement').classList.add('hidden');
  document.getElementById('pm-statement').innerHTML = '';
  document.getElementById('pm-test-results').innerHTML = '';
  document.getElementById('pm-review-btn').classList.add('hidden');
  document.getElementById('pm-code').value = '';

  try {
    const res = await fetch(`/api/problem/cf/${ref}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '문제 로딩 실패');

    _currentProblem.samples = data.samples;
    _currentProblem.title = data.title;

    document.getElementById('pm-title').textContent = data.title;
    document.getElementById('pm-meta').textContent = `${data.time_limit} · ${data.memory_limit}`;
    document.getElementById('pm-loading').classList.add('hidden');

    const samplesHtml = data.samples.map((s, i) => `
      <div class="pm-sample">
        <div class="pm-sample-title">예제 입력 ${i + 1}</div>
        <pre class="pm-pre">${escapeHtml(s.input)}</pre>
        <div class="pm-sample-title">예제 출력 ${i + 1}</div>
        <pre class="pm-pre">${escapeHtml(s.output)}</pre>
      </div>`).join('');

    const stmtEl = document.getElementById('pm-statement');
    stmtEl.innerHTML = `
      <div class="pm-text">${escapeHtml(data.statement_ko).replace(/\n/g, '<br>')}</div>
      ${samplesHtml}`;
    stmtEl.classList.remove('hidden');
  } catch (e) {
    document.getElementById('pm-loading').innerHTML =
      `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

function closeProblemModal() {
  document.getElementById('problem-modal').classList.add('hidden');
}

async function runSamples() {
  if (!_currentProblem?.samples?.length) {
    document.getElementById('pm-test-results').innerHTML =
      '<div class="alert alert-info">예제 데이터가 없습니다.</div>';
    return;
  }

  const code = document.getElementById('pm-code').value.trim();
  if (!code) {
    document.getElementById('pm-test-results').innerHTML =
      '<div class="alert alert-info">코드를 먼저 작성해주세요.</div>';
    return;
  }

  const language = document.getElementById('pm-language').value;
  const btn = document.getElementById('pm-run-btn');
  const resultsEl = document.getElementById('pm-test-results');

  btn.disabled = true;
  btn.textContent = '실행 중...';
  resultsEl.innerHTML = '';
  document.getElementById('pm-review-btn').classList.add('hidden');

  let allPassed = true;

  for (let i = 0; i < _currentProblem.samples.length; i++) {
    const sample = _currentProblem.samples[i];
    const tcId = `tc-${i}`;
    resultsEl.innerHTML += `<div class="test-case pending" id="${tcId}"><span class="spinner" style="width:14px;height:14px;border-width:2px"></span> 테스트 ${i + 1} 실행 중...</div>`;

    try {
      const res = await fetch('/api/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language, stdin: sample.input, timeout_sec: 5 }),
      });
      const result = await res.json();

      const actual = (result.stdout || '').trimEnd();
      const expected = sample.output.trimEnd();
      const passed = actual === expected && result.exit_code === 0;
      if (!passed) allPassed = false;

      const detailHtml = !passed ? `
        <div class="tc-detail">
          <div><b>입력</b><pre>${escapeHtml(sample.input)}</pre></div>
          <div><b>예상 출력</b><pre>${escapeHtml(expected)}</pre></div>
          <div><b>실제 출력</b><pre>${escapeHtml(actual || result.stderr || '(없음)')}</pre></div>
        </div>` : '';

      document.getElementById(tcId).outerHTML = `
        <div class="test-case ${passed ? 'pass' : 'fail'}">
          <span class="tc-badge">${passed ? '✅ 통과' : '❌ 실패'}</span>테스트 ${i + 1}
          <span style="color:var(--text-muted);font-size:.78rem;margin-left:8px">${result.time_ms}ms</span>
          ${detailHtml}
        </div>`;
    } catch (e) {
      allPassed = false;
      document.getElementById(tcId).outerHTML =
        `<div class="test-case fail"><span class="tc-badge">❌</span>테스트 ${i + 1} — 오류: ${escapeHtml(e.message)}</div>`;
    }
  }

  btn.disabled = false;
  btn.textContent = '▶ 예제 실행';

  if (allPassed) {
    document.getElementById('pm-review-btn').classList.remove('hidden');
  }
}

function proceedToReview() {
  if (!_currentProblem) return;

  document.getElementById('problem-platform').value = 'codeforces';
  if (document.getElementById('problem-platform').dispatchEvent)
    document.getElementById('problem-platform').dispatchEvent(new Event('change'));

  document.getElementById('problem-id').value = _currentProblem.ref;
  document.getElementById('code-input').value = document.getElementById('pm-code').value;

  const lang = document.getElementById('pm-language').value;
  document.getElementById('code-language').value = lang === 'cpp' ? 'GNU C++17' : 'Python 3';

  closeProblemModal();

  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(s => {
    s.classList.remove('active');
    s.classList.add('hidden');
  });
  document.querySelector('[data-tab="review"]').classList.add('active');
  const reviewTab = document.getElementById('tab-review');
  reviewTab.classList.remove('hidden');
  reviewTab.classList.add('active');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ── 통계 ── */
const statsBtn = document.getElementById('stats-btn');
statsBtn.dataset.label = '통계 불러오기';

statsBtn.addEventListener('click', async () => {
  const result = document.getElementById('stats-result');
  setLoading(statsBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '실패');
    renderStats(result, data);
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(statsBtn, false);
  }
});

function renderStats(container, data) {
  if (!data.tag_stats || data.tag_stats.length === 0) {
    container.innerHTML = '<div class="alert alert-info">아직 데이터가 없습니다.</div>';
    return;
  }

  // 태그 통계 바
  let barsHtml = data.tag_stats.slice(0, 15).map(s => {
    const poorRatio = s.total_count > 0 ? s.poor_count / s.total_count : 0;
    const goodRatio = 1 - poorRatio;
    const barColor = poorRatio > 0.6 ? 'var(--red)' : poorRatio > 0.3 ? 'var(--yellow)' : 'var(--green)';
    return `
      <div class="stat-bar-row">
        <span class="stat-tag-name" title="${s.tag}">${s.tag}</span>
        <div class="stat-bar-wrap">
          <div class="stat-bar" style="width:${Math.round(poorRatio*100)}%;background:${barColor}"></div>
        </div>
        <span class="stat-counts">✓${s.good_count} ✗${s.poor_count}</span>
      </div>`;
  }).join('');

  // 최근 기록 테이블
  let historyHtml = data.history.map(r => {
    const tc = tierClass(r.tier);
    return `<tr>
      <td><a href="${problemUrl(r)}" target="_blank">${problemLabel(r)}. ${r.title}</a></td>
      <td><span class="tier-badge ${tc}" style="font-size:.75rem">${r.tier_name}</span></td>
      <td class="${effClass(r.efficiency)}">${effLabel(r.efficiency)}</td>
      <td style="color:var(--text-muted);font-size:.82rem">${r.created_at.slice(0,10)}</td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <div class="result-card">
      <div class="summary-grid" style="margin-bottom:24px">
        <div class="summary-item">
          <div class="summary-label">총 리뷰 수</div>
          <div class="summary-value">${data.total_reviews}개</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">평균 레벨</div>
          <div class="summary-value">
            <span class="tier-badge ${tierClass(Math.floor(data.avg_tier))}">${data.avg_tier_name}</span>
          </div>
        </div>
      </div>

      <h3 style="font-size:.95rem;margin-bottom:14px;color:var(--text-muted)">태그별 취약도 (빨간색일수록 취약)</h3>
      ${barsHtml}

      <h3 style="font-size:.95rem;margin:24px 0 12px;color:var(--text-muted)">최근 풀이 기록</h3>
      <table class="history-table">
        <thead><tr><th>문제</th><th>난이도</th><th>평가</th><th>날짜</th></tr></thead>
        <tbody>${historyHtml}</tbody>
      </table>
    </div>`;
}

/* ── 리뷰 기록 ── */
const historyBtn = document.getElementById('history-btn');
historyBtn.dataset.label = '기록 불러오기';
historyBtn.addEventListener('click', loadHistory);

let allReviewProblems = [];

async function loadHistory() {
  const list = document.getElementById('history-list');
  setLoading(historyBtn, true);
  list.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const res = await fetch('/api/reviews/grouped');
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch(e) { throw new Error('서버 응답 오류: ' + text.slice(0,100)); }
    if (!res.ok) throw new Error(data.detail || '실패');
    allReviewProblems = data.problems || [];
    renderHistoryControls(list);
    renderProblemList(list, getFilteredReviews());
  } catch (e) {
    showError(list, e.message);
  } finally {
    setLoading(historyBtn, false);
  }
}

function renderHistoryControls(container) {
  const ctrl = document.createElement('div');
  ctrl.id = 'history-controls';
  ctrl.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center';
  ctrl.innerHTML = `
    <input id="h-search" type="text" placeholder="제목 또는 태그 검색..." style="flex:1;min-width:140px;padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);font-size:.85rem" />
    <select id="h-tier" style="padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);font-size:.85rem">
      <option value="">전체 난이도</option>
      <option value="bronze">브론즈</option>
      <option value="silver">실버</option>
      <option value="gold">골드</option>
      <option value="platinum">플래티넘</option>
      <option value="diamond">다이아</option>
    </select>
    <select id="h-eff" style="padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);font-size:.85rem">
      <option value="">전체 효율</option>
      <option value="good">효율적</option>
      <option value="ok">보통</option>
      <option value="poor">비효율적</option>
    </select>
    <select id="h-sort" style="padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);font-size:.85rem">
      <option value="recent">최근순</option>
      <option value="tier_desc">난이도 높은순</option>
      <option value="tier_asc">난이도 낮은순</option>
      <option value="pid_asc">문제 번호순</option>
    </select>`;
  container.innerHTML = '';
  container.appendChild(ctrl);

  ['h-search','h-tier','h-eff','h-sort'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      renderProblemList(container, getFilteredReviews());
    });
  });
}

function getFilteredReviews() {
  const q = (document.getElementById('h-search')?.value || '').toLowerCase();
  const tier = document.getElementById('h-tier')?.value || '';
  const eff = document.getElementById('h-eff')?.value || '';
  const sort = document.getElementById('h-sort')?.value || 'recent';

  const TIER_GROUP = { bronze:[1,5], silver:[6,10], gold:[11,15], platinum:[16,20], diamond:[21,25] };

  let list = allReviewProblems.filter(p => {
    if (q && !`${problemLabel(p)} ${p.title} ${(p.tags||[]).join(' ')}`.toLowerCase().includes(q)) return false;
    if (tier) {
      const [lo,hi] = TIER_GROUP[tier] || [0,30];
      if (p.tier < lo || p.tier > hi) return false;
    }
    if (eff) {
      const lastEff = (p.efficiencies || '').split(',')[0] || 'ok';
      if (lastEff !== eff) return false;
    }
    return true;
  });

  if (sort === 'recent') list.sort((a,b) => b.last_submitted.localeCompare(a.last_submitted));
  else if (sort === 'tier_desc') list.sort((a,b) => b.tier - a.tier);
  else if (sort === 'tier_asc') list.sort((a,b) => a.tier - b.tier);
  else if (sort === 'pid_asc') list.sort((a,b) => problemLabel(a).localeCompare(problemLabel(b), undefined, { numeric: true }));
  return list;
}

function renderProblemList(container, problems) {
  // 기존 카드만 제거 (컨트롤은 유지)
  container.querySelectorAll('.history-card, .alert').forEach(el => el.remove());

  if (!problems || problems.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'alert alert-info';
    empty.textContent = '아직 리뷰 기록이 없습니다.';
    container.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  problems.forEach(p => {
    const tc = tierClass(p.tier);
    const effList = (p.efficiencies || '').split(',');
    const lastEff = effList[0] || 'ok';
    const div = document.createElement('div');
    div.className = 'history-card';
    div.dataset.platform = p.platform || 'boj';
    div.dataset.problemRef = p.problem_ref || String(p.problem_id || '');
    div.style.cursor = 'pointer';
    div.innerHTML = `
      <div class="history-card-info">
        <div class="history-card-title">
          <a href="${problemUrl(p)}" target="_blank"
             style="color:inherit;text-decoration:none"
             onclick="event.stopPropagation()">
            ${problemLabel(p)}. ${p.title}
          </a>
        </div>
        <div class="history-card-meta">${(p.tags || []).slice(0,3).join(' · ')}</div>
      </div>
      <div class="history-card-right">
        <span class="tier-badge ${tc}" style="font-size:.75rem">${p.tier_name}</span>
        <span class="${effClass(lastEff)}" style="font-size:.82rem">${effLabel(lastEff)}</span>
        <span style="font-size:.78rem;color:var(--text-muted)">
          제출 ${p.submission_count}회 · ${p.last_submitted.slice(0,10)}
        </span>
      </div>`;
    div.addEventListener('click', () => openProblemModal(div.dataset.platform, div.dataset.problemRef));
    frag.appendChild(div);
  });
  container.appendChild(frag);
}

async function openProblemModal(platform, problemRef) {
  const modal = document.getElementById('review-modal');
  const content = document.getElementById('modal-content');
  modal.classList.remove('hidden');
  content.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const res = await fetch(`/api/reviews/problem/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '실패');
    const reviews = data.reviews;
    if (!reviews.length) throw new Error('기록이 없습니다.');

    const first = reviews[0];
    const tc = tierClass(first.tier);
    const tagsHtml = (first.tags || []).map(t => `<span class="tag">${t}</span>`).join('');

    // 제출 선택 탭
    const tabsHtml = reviews.map((r, i) => `
      <button class="submission-tab ${i === 0 ? 'active' : ''}" data-idx="${i}">
        <span style="font-weight:600">제출 ${reviews.length - i}회차</span>
        <span class="${effClass(r.efficiency)}" style="font-size:.78rem">${effLabel(r.efficiency)}</span>
        <span style="color:var(--text-muted);font-size:.75rem">${r.created_at.slice(0,10)}</span>
      </button>`).join('');

    content.innerHTML = `
      <div class="problem-header" style="margin-bottom:12px">
        <span class="problem-title">
          <a href="${problemUrl(first)}" target="_blank" style="color:inherit;text-decoration:none">
            ${problemLabel(first)}. ${first.title}
          </a>
        </span>
        <span class="tier-badge ${tc}">${first.tier_name}</span>
        <span style="font-size:.82rem;color:var(--text-muted);margin-left:auto">총 ${reviews.length}회 제출</span>
      </div>
      <div class="tag-list" style="margin-bottom:16px">${tagsHtml || '<span class="tag">태그 없음</span>'}</div>
      <div class="submission-tabs">${tabsHtml}</div>
      <div id="submission-detail-area"></div>`;

    function renderDetail(idx) {
      const r = reviews[idx];
      const sl = (r.strengths || []).map(s => `<li>${s}</li>`).join('');
      const wl = (r.weaknesses || []).map(w => `<li>${w}</li>`).join('');
      const hasPoints = sl || wl;
      document.getElementById('submission-detail-area').innerHTML = `
        <div class="summary-grid" style="margin:16px 0">
          <div class="summary-item">
            <div class="summary-label">효율성</div>
            <div class="summary-value ${effClass(r.efficiency)}">${effLabel(r.efficiency)}</div>
          </div>
          ${r.complexity ? `<div class="summary-item"><div class="summary-label">시간복잡도</div><div class="summary-value">${r.complexity}</div></div>` : ''}
          ${r.better_algorithm ? `<div class="summary-item"><div class="summary-label">더 나은 알고리즘</div><div class="summary-value" style="font-size:.82rem;color:var(--yellow)">${r.better_algorithm}</div></div>` : ''}
        </div>
        ${hasPoints ? `
        <div class="points-grid" style="margin-bottom:16px">
          <div class="points-box good"><h4>✓ 잘한 점</h4><ul>${sl || '<li>-</li>'}</ul></div>
          <div class="points-box bad"><h4>✗ 개선할 점</h4><ul>${wl || '<li>-</li>'}</ul></div>
        </div>` : ''}
        <div class="feedback-box" style="margin-bottom:16px">
          <h4>피드백</h4>
          <div class="markdown-body">${marked.parse(r.feedback || '')}</div>
        </div>
        <div>
          <h4 style="font-size:.85rem;color:var(--text-muted);margin-bottom:8px">제출 코드</h4>
          <pre class="code-block">${escapeHtml(r.code)}</pre>
        </div>`;
    }

    content.querySelectorAll('.submission-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        content.querySelectorAll('.submission-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderDetail(Number(btn.dataset.idx));
      });
    });

    renderDetail(0);
  } catch (e) {
    content.innerHTML = `<div class="alert alert-error">❌ ${e.message}</div>`;
  }
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('review-modal').classList.add('hidden');
});
document.getElementById('review-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
});

/* ── BaekjoonHub GitHub 가져오기 ── */
const ghImportBtn = document.getElementById('gh-import-btn');
ghImportBtn.dataset.label = 'GitHub에서 가져오기';

ghImportBtn.addEventListener('click', async () => {
  const repo = document.getElementById('gh-repo').value.trim();
  const token = document.getElementById('gh-token').value.trim();
  const result = document.getElementById('gh-import-result');

  if (!repo) { showError(result, 'GitHub 저장소 주소를 입력하세요.'); return; }

  setLoading(ghImportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> GitHub에서 파일 목록을 가져오는 중...</div>';

  try {
    const res = await fetch('/api/import-github', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo, token: token || null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '실패');

    const failMsg = data.failed && data.failed.length > 0
      ? `<br><span style="color:var(--text-muted);font-size:.82rem">정보 조회 실패: ${data.failed.length}개</span>`
      : '';
    result.innerHTML = `
      <div class="alert alert-info" style="color:var(--green)">
        ✅ 완료! 저장소에서 <b>${data.total_found}</b>개 발견 →
        <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음${failMsg}
      </div>
      <button id="gh-reimport-btn" class="btn-primary" style="margin-top:8px;background:var(--red)">
        🗑 기존 기록 전체 삭제 후 다시 가져오기
      </button>`;
    document.getElementById('gh-reimport-btn').addEventListener('click', async () => {
      if (!confirm('가져온 기록을 전부 삭제하고 다시 가져옵니다. 계속할까요?')) return;
      await fetch('/api/solved-history', { method: 'DELETE' });
      ghImportBtn.click();
    });
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(ghImportBtn, false);
  }
});

/* ── 기록 가져오기 ── */
const importBtn = document.getElementById('import-btn');
importBtn.dataset.label = '가져오기';

importBtn.addEventListener('click', async () => {
  const bojId = document.getElementById('import-boj-id').value.trim();
  const cookie = document.getElementById('import-cookie').value.trim();
  const pages = Number(document.getElementById('import-pages').value);
  const result = document.getElementById('import-result');

  if (!bojId) { showError(result, 'BOJ 아이디를 입력하세요.'); return; }

  setLoading(importBtn, true);
  const pageDesc = pages >= 9999 ? '전체' : `최대 ${pages * 20}개`;
  result.innerHTML = `<div class="alert alert-info"><span class="spinner"></span> 제출 기록을 가져오는 중입니다... (${pageDesc}, 기록이 많으면 수 분 소요)</div>`;

  try {
    const res = await fetch('/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boj_id: bojId, session_cookie: cookie || null, max_pages: pages }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '가져오기 실패');

    const failMsg = data.failed && data.failed.length > 0
      ? `<br><span style="color:var(--text-muted);font-size:.82rem">정보 조회 실패: ${data.failed.join(', ')}</span>`
      : '';
    const bojGithubMsg = (data.github_pushed > 0)
      ? `<br><span style="color:var(--green);font-size:.82rem">🐙 GitHub <b>${data.github_repo}</b>에 <b>${data.github_pushed}</b>개 push 완료 (BOJ/ 폴더)</span>`
      : '';
    result.innerHTML = `
      <div class="alert alert-info" style="color:var(--green)">
        ✅ 완료! 총 <b>${data.total_found}</b>개 발견 →
        <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음${failMsg}${bojGithubMsg}
      </div>`;
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(importBtn, false);
  }
});

const cfImportBtn = document.getElementById('cf-import-btn');
if (cfImportBtn) {
  cfImportBtn.dataset.label = 'Codeforces에서 가져오기';
  cfImportBtn.addEventListener('click', async () => {
    const handle = document.getElementById('cf-handle').value.trim();
    const count = Number(document.getElementById('cf-count').value);
    const apiKey = document.getElementById('cf-api-key').value.trim();
    const apiSecret = document.getElementById('cf-api-secret').value.trim();
    const result = document.getElementById('cf-import-result');

    if (!handle) { showError(result, 'Codeforces handle을 입력하세요.'); return; }

    setLoading(cfImportBtn, true);
    result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> Codeforces 제출 기록을 가져오는 중입니다...</div>';

    const ghRepo = (document.getElementById('cf-gh-repo')?.value || '').trim();
    const ghToken = (document.getElementById('cf-gh-token')?.value || '').trim();

    try {
      const res = await fetch('/api/import-codeforces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          handle,
          count,
          api_key: apiKey || null,
          api_secret: apiSecret || null,
          github_repo: ghRepo || null,
          github_token: ghToken || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '가져오기 실패');

      const sourceMsg = data.has_source
        ? '<br><span style="color:var(--text-muted);font-size:.82rem">소스 코드 포함 항목이 있어 AI 리뷰까지 바로 이어갈 수 있습니다.</span>'
        : '<br><span style="color:var(--text-muted);font-size:.82rem">현재는 코드 없이 기록만 가져왔습니다. API Key/Secret을 넣으면 본인 계정 소스 코드도 함께 가져올 수 있습니다.</span>';

      const githubMsg = (data.github_pushed > 0)
        ? `<br><span style="color:var(--green);font-size:.82rem">🐙 GitHub <b>${data.github_repo}</b>에 <b>${data.github_pushed}</b>개 push 완료 (Codeforces/ 폴더)</span>`
        : '';

      result.innerHTML = `
        <div class="alert alert-info" style="color:var(--green)">
          ✅ 완료! <b>${data.handle}</b>의 Codeforces 기록 <b>${data.total_found}</b>개 확인 →
          <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음
          ${sourceMsg}${githubMsg}
        </div>`;
      loadImportedHistory();
    } catch (e) {
      showError(result, e.message);
    } finally {
      setLoading(cfImportBtn, false);
    }
  });
}

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
      bronze: [1, 5], silver: [6, 10], gold: [11, 15],
      platinum: [16, 20], diamond: [21, 25], ruby: [26, 30], unrated: [0, 0],
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

      let html = '';
      // 이전 버튼
      html += `<button class="page-btn" ${importPage === 1 ? 'disabled' : ''} data-page="${importPage - 1}">‹</button>`;

      // 페이지 번호 (최대 7개 표시)
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
                <a href="${problemUrl(p)}" target="_blank"
                   style="color:inherit;text-decoration:none">
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

      // 코드 보기 버튼
      container.querySelectorAll('.btn-view-code').forEach(btn => {
        btn.addEventListener('click', () => toggleCodeView(btn));
      });

      // AI 리뷰 버튼
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

    // 페이지당 개수 변경
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

    // 리뷰 완료 → 카드 제거 (서버에서도 solved_history에서 삭제됨)
    card.nextElementSibling?.remove();
    card.remove();
    btn.textContent = '✓ 완료';
  } catch (e) {
    btn.textContent = 'AI 리뷰';
    btn.disabled = false;
    alert('오류: ' + e.message);
  }
}

/* ── 종합 리포트 ── */
const reportBtn = document.getElementById('report-btn');
reportBtn.dataset.label = '리포트 생성';

reportBtn.addEventListener('click', async () => {
  const result = document.getElementById('report-result');
  setLoading(reportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 종합 분석 중입니다... (10~20초 소요)</div>';

  try {
    const res = await fetch('/api/report');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '실패');
    result.innerHTML = `
      <div class="result-card">
        <div class="feedback-box">
          <h4>📊 종합 분석 리포트</h4>
          <div class="markdown-body">${marked.parse(data.report)}</div>
        </div>
      </div>`;
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(reportBtn, false);
  }
});
