# BOJ / Codeforces 코드 리뷰 & 문제 추천

알고리즘 풀이 코드를 AI로 분석하고, 학습 기록을 바탕으로 약한 태그를 추적하는 웹앱입니다.

현재 지원 범위:
- `BOJ`: 코드 리뷰, 문제 추천, 통계, 제출 기록 import
- `Codeforces`: 코드 리뷰, 문제 추천, 통계, 제출 기록 import, 자동 제출

## 주요 기능

- **코드 리뷰**
  - BOJ 또는 Codeforces 문제 번호와 코드를 입력하면 AI가 시간복잡도, 효율성, 개선점, 강점/약점을 분석합니다.
- **CF 인앱 문제 뷰어**
  - Codeforces 문제를 앱 내에서 바로 보고 한국어 번역까지 제공합니다.
  - 예제 입출력 직접 실행 (Python / C++) 지원
- **CF 자동 제출**
  - 코드를 작성한 뒤 버튼 한 번으로 Codeforces에 직접 제출합니다.
  - `CODEFORCES_HANDLE` / `CODEFORCES_PASSWORD` 환경변수로 자동 로그인
- **기록 import**
  - `BaekjoonHub GitHub` 저장소 import
  - `BOJ 제출 기록` import
  - `Codeforces handle` 기반 import
- **리뷰 기록 조회**
  - 문제별 제출 이력과 상세 피드백을 다시 확인할 수 있습니다.
- **통계 / 리포트**
  - BOJ / Codeforces 플랫폼 전환 탭 제공
  - 태그 통계, 티어(레이팅) 변화, 누적 분석 리포트
- **문제 추천**
  - 약한 태그와 현재 수준 + 도전 난이도를 혼합해 다음 문제를 추천합니다.
  - BOJ / Codeforces 각각 지원

## 로컬 실행

### 1. 요구사항

- Python 3.11+
- OpenAI API 키

### 2. 설치

```bash
git clone https://github.com/SIDED00R/boj-code-review.git
cd boj-code-review

python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일을 만듭니다.

```env
OPENAI_API_KEY=your_openai_key

# 선택: Codeforces 소스 코드 import
CODEFORCES_API_KEY=your_codeforces_key
CODEFORCES_API_SECRET=your_codeforces_secret

# 선택: CF 자동 제출
CODEFORCES_HANDLE=your_cf_handle_or_email
CODEFORCES_PASSWORD=your_cf_password

# 선택: PostgreSQL 사용 시
# DB_TYPE=postgres
# DB_NAME=boj_review
# DB_USER=boj_user
# DB_PASSWORD=your_password
# DB_HOST=localhost
# DB_PORT=5432
# DB_SOCKET=/cloudsql/PROJECT:REGION:INSTANCE
```

### 4. 실행

```bash
python -m uvicorn server:app --reload
```

브라우저에서 `http://localhost:8000` 접속

## Codeforces 관련 주의사항

- CF 문제 본문은 공식 API가 제공하지 않으므로 크롤링으로 가져옵니다.
  - 실패 시 리뷰 화면의 `문제 설명` 입력칸에 직접 붙여 넣어도 됩니다.
- CF 자동 제출은 Cloudflare 상태에 따라 차단될 수 있습니다.
- CF 소스코드 import는 본인 계정 API Key / Secret이 필요합니다.

## 배포

### Cloud Run + Cloud SQL

이 프로젝트는 GCP Cloud Run + Cloud SQL(PostgreSQL) 구성으로 배포할 수 있습니다.

```bash
gcloud run deploy boj-review \
  --source . \
  --region asia-northeast3 \
  --add-cloudsql-instances PROJECT:REGION:INSTANCE
```

필수 환경변수:

```env
OPENAI_API_KEY=...
DB_TYPE=postgres
DB_NAME=boj_review
DB_USER=boj_user
DB_PASSWORD=...
DB_SOCKET=/cloudsql/PROJECT:REGION:INSTANCE

# GitHub OAuth (선택)
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
APP_URL=https://your-cloud-run-url

# CF 자동 제출 (선택)
CODEFORCES_HANDLE=...
CODEFORCES_PASSWORD=...
CODEFORCES_API_KEY=...
CODEFORCES_API_SECRET=...
```

## 프로젝트 구조

```
.
├── server.py                  # FastAPI 앱 진입점 (라우터 등록만)
├── db.py                      # DB 초기화 / 쿼리
├── api_client.py              # 외부 API 클라이언트 (BOJ, CF, OpenAI)
├── recommender.py             # 문제 추천 로직
├── cf_submitter.py            # CF 자동 제출 (requests 기반)
├── routes/
│   ├── auth.py                # GitHub OAuth
│   ├── review.py              # 코드 리뷰 & GitHub push
│   ├── problem.py             # CF 문제 조회 & 번역
│   ├── execute.py             # 코드 실행 (Python / C++)
│   ├── recommend.py           # 문제 추천
│   ├── history.py             # 리뷰 기록 조회
│   ├── solved.py              # import된 제출 기록 관리
│   ├── import_routes.py       # GitHub / BOJ / CF import
│   ├── stats.py               # 통계 & 종합 리포트
│   └── cf_submit.py           # CF 제출 API
└── static/
    ├── index.html
    ├── style.css
    └── js/
        ├── utils.js           # 공유 유틸
        ├── editor.js          # CodeMirror 에디터
        ├── theme.js           # 다크/라이트 모드
        ├── tabs.js            # 탭 전환
        ├── github.js          # GitHub 연결 UI
        ├── tier-chart.js      # 티어 변화 차트
        ├── review.js          # 코드 리뷰 탭
        ├── recommend.js       # 문제 추천 탭
        ├── problem-modal.js   # CF 문제 뷰어 모달
        ├── cf-submit.js       # CF 자동 제출
        ├── stats.js           # 풀이 통계 탭
        ├── history.js         # 리뷰 기록 탭
        ├── import.js          # 기록 import 탭
        └── report.js          # 종합 리포트 탭
```

> 각 파일은 단일 기능만 담당합니다 (Single Responsibility Principle).

## 기술 스택

- Backend: FastAPI + Uvicorn
- Frontend: HTML / CSS / Vanilla JS
- AI: OpenAI API
- BOJ 데이터: solved.ac API
- Codeforces 데이터: Codeforces API + 크롤링
- CF 제출: requests 라이브러리 (Cloudflare 상태에 따라 동작)
- DB: SQLite (로컬) / PostgreSQL (배포)

## 환경변수 전체 목록

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | AI 리뷰용 OpenAI 키 |
| `CODEFORCES_API_KEY` | 선택 | CF 소스코드 import용 |
| `CODEFORCES_API_SECRET` | 선택 | CF 소스코드 import용 |
| `CODEFORCES_HANDLE` | 선택 | CF 자동 제출용 이메일 또는 핸들 |
| `CODEFORCES_PASSWORD` | 선택 | CF 자동 제출용 비밀번호 |
| `GITHUB_CLIENT_ID` | 선택 | GitHub OAuth |
| `GITHUB_CLIENT_SECRET` | 선택 | GitHub OAuth |
| `APP_URL` | 선택 | GitHub OAuth 콜백 URL |
| `DB_TYPE` | 선택 | `sqlite`(기본) 또는 `postgres` |
| `DB_NAME` | 선택 | PostgreSQL DB 이름 |
| `DB_USER` | 선택 | PostgreSQL 사용자 |
| `DB_PASSWORD` | 선택 | PostgreSQL 비밀번호 |
| `DB_HOST` | 선택 | PostgreSQL 호스트 |
| `DB_PORT` | 선택 | PostgreSQL 포트 |
| `DB_SOCKET` | 선택 | Cloud SQL Unix socket 경로 |

## 라이선스

MIT
