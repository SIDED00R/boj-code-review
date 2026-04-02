# 🧠 BOJ 코드 리뷰 & 문제 추천

백준 알고리즘 문제 풀이 코드를 AI로 분석하고, 취약 알고리즘 태그를 기반으로 맞춤 문제를 추천해주는 웹 앱입니다.

![demo](assets/demo.gif)

## 주요 기능

- **코드 리뷰** — 문제 번호 + 코드 입력 시 AI가 시간복잡도, 알고리즘 적합성, 코드 품질 분석
- **문제 추천** — 풀이 수·최근성·AI 효율 점수를 조합한 취약 태그 기반 맞춤 추천
- **풀이 가져오기** — BaekjoonHub GitHub 연동 또는 BOJ 직접 크롤링으로 기존 풀이 일괄 import
- **통계** — 태그별 강점 / 취약점 시각화 + 티어 변화 그래프
- **종합 리포트** — AI가 누적 데이터를 분석해 학습 방향 제안
- **리뷰 기록** — 문제별로 묶인 제출 기록과 피드백 열람, 검색·필터·정렬 지원

---

## 로컬 실행 (SQLite — 별도 DB 설치 불필요)

### 1. 필수 조건

- Python 3.11+
- AI API 토큰 (아래 지원 서비스 중 선택)

| 서비스 | 발급 링크 | 기본 모델 |
|--------|-----------|-----------|
| OpenAI | [platform.openai.com](https://platform.openai.com) | gpt-4o |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) | claude-sonnet |

### 2. 설치

```bash
git clone https://github.com/SIDED00R/boj-code-review.git
cd boj-code-review

python -m venv venv

# Windows
./venv/Scripts/activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 사용하는 AI 서비스의 API 토큰을 입력하세요:

```
# OpenAI 사용 시
OPENAI_API_KEY=sk-proj-...

# Anthropic 사용 시 (analyzer.py 모델 변경 필요)
ANTHROPIC_API_KEY=sk-ant-...
```

> **참고:** 기본 설정은 OpenAI GPT-4o입니다. 다른 AI를 사용하려면 `analyzer.py`의 모델 설정을 변경하세요.

### 4. 실행

```bash
python -m uvicorn server:app --reload
```

브라우저에서 **http://localhost:8000** 접속

---

## 클라우드 배포 (PostgreSQL 사용)

### GCP Cloud Run + Cloud SQL

1. Cloud SQL PostgreSQL 인스턴스 생성
2. 데이터베이스 및 유저 생성
3. `.env`에 아래 환경변수 추가:

```
DB_TYPE=postgres
DB_NAME=boj_review
DB_USER=boj_user
DB_PASSWORD=your_password
DB_HOST=your_cloud_sql_ip   # 로컬 테스트용
DB_SOCKET=/cloudsql/PROJECT:REGION:INSTANCE  # Cloud Run 배포용
```

4. Docker 이미지 빌드 & Cloud Run 배포:

```bash
docker build -t gcr.io/YOUR_PROJECT/boj-review .
docker push gcr.io/YOUR_PROJECT/boj-review

gcloud run deploy boj-review \
  --image=gcr.io/YOUR_PROJECT/boj-review \
  --platform=managed \
  --region=asia-northeast3 \
  --allow-unauthenticated \
  --add-cloudsql-instances=PROJECT:REGION:INSTANCE \
  --set-env-vars="OPENAI_API_KEY=...,DB_TYPE=postgres,DB_NAME=boj_review,DB_USER=boj_user,DB_PASSWORD=...,DB_SOCKET=/cloudsql/PROJECT:REGION:INSTANCE"
```

### 기타 클라우드 (AWS, Azure 등)

PostgreSQL DB를 준비하고 환경변수만 맞게 설정하면 동일하게 동작합니다.

---

## 기술 스택

| 항목 | 기술 |
|------|------|
| 백엔드 | FastAPI + uvicorn |
| AI 분석 | OpenAI / Anthropic 등 (교체 가능) |
| 문제 정보 | solved.ac API + BeautifulSoup |
| DB (로컬) | SQLite |
| DB (클라우드) | PostgreSQL |
| 프론트엔드 | Vanilla JS + 다크 테마 CSS |

---

## 환경변수 목록

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `OPENAI_API_KEY` | ✅ | AI API 토큰 |
| `DB_TYPE` | ❌ | `sqlite`(기본) 또는 `postgres` |
| `DB_NAME` | ❌ | PostgreSQL DB 이름 (기본: `boj_review`) |
| `DB_USER` | ❌ | PostgreSQL 유저 (기본: `boj_user`) |
| `DB_PASSWORD` | ❌ | PostgreSQL 비밀번호 |
| `DB_HOST` | ❌ | PostgreSQL 호스트 (TCP 연결) |
| `DB_PORT` | ❌ | PostgreSQL 포트 (기본: `5432`) |
| `DB_SOCKET` | ❌ | Cloud SQL Unix 소켓 경로 |

---

## 라이선스

MIT
