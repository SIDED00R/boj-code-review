from pydantic import BaseModel, validator


class ReviewRequest(BaseModel):
    platform: str = "boj"
    problem_id: int | None = None
    problem_ref: str | None = None
    problem_statement: str | None = None
    code: str


class ImportRequest(BaseModel):
    boj_id: str
    session_cookie: str | None = None
    max_pages: int = 5


class GithubImportRequest(BaseModel):
    repo: str
    token: str | None = None


class CodeforcesImportRequest(BaseModel):
    handle: str
    count: int = 200
    api_key: str | None = None
    api_secret: str | None = None
    github_repo: str | None = None
    github_token: str | None = None


class SetRepoRequest(BaseModel):
    repo: str


class PushReviewRequest(BaseModel):
    platform: str
    problem_ref: str
    title: str
    tier_name: str
    tags: list[str] = []
    code: str
    language: str = ""
    url: str = ""
    description: str = ""
    input_desc: str = ""
    output_desc: str = ""


class ExecuteRequest(BaseModel):
    code: str
    language: str = "python3"
    stdin: str = ""
    timeout_sec: int = 5

    @validator("code")
    def code_max_length(cls, v):
        if len(v) > 50_000:
            raise ValueError("코드는 50,000자를 초과할 수 없습니다.")
        return v

    @validator("stdin")
    def stdin_max_length(cls, v):
        if len(v) > 10_000:
            raise ValueError("입력은 10,000자를 초과할 수 없습니다.")
        return v

    @validator("timeout_sec")
    def timeout_bounds(cls, v):
        return max(1, min(v, 10))


class ReviewResponse(BaseModel):
    problem_id: int
    platform: str
    problem_ref: str
    problem_url: str
    title: str
    tier: int
    tier_name: str
    tags: list[str]
    efficiency: str
    complexity: str
    better_algorithm: str | None
    feedback: str
    strengths: list[str]
    weaknesses: list[str]
