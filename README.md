# 국내 여행 추천 프로그램

LLM API(OpenAI, `litellm` 경유)와 지도/장소 검색 API(Kakao Local)를 조합하여, 입력한 날짜를 기준으로 국내 여행지를
추천하고 해당 지역의 맛집을 검색한 뒤 최종 여행 리포트(Markdown)를 생성하는 CLI 프로그램입니다. 모든 LLM 호출은
`litellm`을 통해 이루어지며, [Langfuse](https://langfuse.com)로 트레이싱(trace/span/generation)됩니다.

## 1. 프로그램 개요

여행 날짜(`-date`)를 입력하면 다음 순서로 동작합니다.

1. **1차 추천 (LLM)**: 입력한 날짜를 기준으로 여행하기 좋은 국내 도시, 날씨 요약, 행사/축제, 추천 이유를
   JSON 형식으로 생성합니다.
2. **맛집 검색 (Kakao Local)**: 1차 추천 결과의 `recommended_city`를 키워드로 맛집 최대 5곳을 검색합니다.
   검색 결과가 없거나 API 호출이 실패해도 프로그램은 중단되지 않고 "데이터 없음"으로 다음 단계로 진행합니다.
3. **최종 리포트 생성 (LLM)**: 1차 추천 결과와 맛집 목록을 종합하여 Markdown 형식의 최종 여행 리포트를 생성합니다.

실행 결과는 `results/` 폴더에 저장됩니다.

- `results/{date}_travel_data.json`: 1차 추천 JSON, 맛집 검색 결과, 오류 요약(`errors`)을 포함한 원본 데이터
- `results/{date}_travel_plan.md`: 최종 여행 리포트 (Markdown)

### 프로젝트 구조

```
travel_planner.py                        # CLI 엔트리포인트 (argparse + 전체 흐름 오케스트레이션)
project_config/
  settings.py                            # pydantic-settings 기반 환경변수/설정
  prompts.yml                            # LLM 프롬프트 텍스트 (코드와 분리)
utils/
  prompt.py                              # prompts.yml 로더 + 변수 치환
  llm_client.py                          # litellm 호출 + Langfuse generation 기록 + 폴백 리포트
  connection/
    kakao_client.py                      # Kakao Local 맛집 검색 클라이언트
    langfuse_manager.py                  # Langfuse 클라이언트 싱글톤 (미설정/장애 시 NoOp)
```

## 2. 실행 방법

### 2-1. 의존성 설치

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2-2. API 키 설정

아래 "3. API 키 설정 방법"을 먼저 진행하세요.

### 2-3. 실행

```bash
python travel_planner.py --date "2026-03-15"
# 또는
python travel_planner.py -date "2026-03-15"
```

날짜 형식(`YYYY-MM-DD`)이 올바르지 않거나, 오늘보다 과거 날짜이면 사용법 안내를 출력하고 종료합니다.

실행 예시:

```
[1/3] 1차 추천 생성 중(LLM)...
    - recommended_city: "제주"
[2/3] 맛집 검색 중(지도/장소 API)...
    - 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
    - 리포트 생성 완료

완료! results/2026-03-15_travel_plan.md 를 확인하세요.
원본 데이터: results/2026-03-15_travel_data.json
```

## 3. API 키 설정 방법

이 프로그램은 아래 API 키가 필요합니다. `OPENAI_API_KEY`/`KAKAO_REST_API_KEY`는 필수이며, `LANGFUSE_*`는
트레이싱 기능을 쓰려면 필요합니다(미설정 시 트레이싱만 자동으로 비활성화되고 프로그램은 정상 동작합니다).

| 환경변수 | 설명 | 발급처 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 (`litellm`을 통해 호출) | https://platform.openai.com/api-keys |
| `KAKAO_REST_API_KEY` | Kakao Local(장소 검색) REST API 키 | https://developers.kakao.com (내 애플리케이션 > REST API 키) |
| `OPENAI_MODEL` (선택) | 사용할 OpenAI 모델. 미설정 시 `gpt-4o-mini` 사용 | - |
| `LANGFUSE_HOST` (선택) | Langfuse 서버 주소. 미설정 시 사내 인스턴스(`http://192.168.10.20:3000`) 사용 | 사내 Langfuse |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (선택) | Langfuse 프로젝트 API 키 | Langfuse 웹 콘솔 > Settings > API Keys |

### 방법 A. `.env` 파일 사용 (권장)

프로젝트 루트에 `.env.example`을 복사해 `.env` 파일을 만들고, 실제 발급받은 키 값으로 채워 넣습니다.

```bash
cp .env.example .env
```

`.env` 파일 내용 예시 (실제 키 값은 본인 것으로 교체):

```
OPENAI_API_KEY=sk-...
KAKAO_REST_API_KEY=...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

`python-dotenv`와 `pydantic-settings`가 실행 시 `.env` 파일을 자동으로 읽어 환경변수로 등록합니다. `.env` 파일은
`.gitignore`에 등록되어 있어 git에 커밋되지 않습니다.

### 방법 B. 환경변수 직접 설정

macOS/Linux (현재 터미널 세션에만 적용):

```bash
export OPENAI_API_KEY="YOUR_KEY"
export KAKAO_REST_API_KEY="YOUR_KEY"
```

Windows PowerShell (현재 세션에만 적용):

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
$env:KAKAO_REST_API_KEY="YOUR_KEY"
```

`OPENAI_API_KEY`/`KAKAO_REST_API_KEY` 중 하나라도 설정되어 있지 않으면 프로그램은 API를 호출하지 않고 즉시
종료하며, 위 설정 방법을 화면에 안내합니다. `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`가 없으면 트레이싱은
자동으로 NoOp(아무 동작도 하지 않음) 처리되어 프로그램 실행에는 영향을 주지 않습니다.

### Langfuse 트레이싱 확인 방법

1. 위 방법 A/B로 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`를 설정합니다. (`LANGFUSE_HOST`는 기본값이
   사내 인스턴스 `http://192.168.10.20:3000`로 지정되어 있어 별도 설정하지 않아도 됩니다.)
2. 프로그램을 실행합니다.
3. 브라우저에서 `http://192.168.10.20:3000`에 접속해 프로젝트를 선택하면, `travel_planner`라는 이름의
   trace 아래에 `first_recommendation`(1차 추천 LLM 호출) → `place_search`(맛집 검색) →
   `report_generation`(최종 리포트 LLM 호출) 3개의 span과, 각 LLM 호출에 대응하는 generation 기록을 확인할 수
   있습니다.

### ⚠️ API 키 유출 주의 사항

- **API 키(OpenAI/Kakao/Langfuse 모두 포함)를 코드에 직접 작성하지 마세요.** 반드시 `.env` 또는 환경변수로만
  관리합니다. (`project_config/settings.py`가 유일하게 환경변수를 읽는 지점이며, 여기에도 키 값은 하드코딩하지
  않습니다.)
- `.env` 파일은 절대 커밋/공유/제출하지 않습니다. (`.gitignore`에 이미 등록되어 있습니다.)
- `README.md`, 커밋 메시지, 로그, 결과 파일(`results/` 내 JSON/Markdown) 어디에도 실제 키 값이 남지 않도록 주의하세요.
  본 프로그램은 키 값을 결과물에 출력하지 않으며, Langfuse에 전송되는 trace에도 프롬프트/응답 내용만 담기고
  API 키 자체는 포함되지 않습니다.
- 키가 실수로 노출되었다면 즉시 발급처(OpenAI/Kakao Developers/Langfuse)에서 키를 폐기하고 재발급하세요.
- 키가 유출되면 과금/쿼터 초과 등의 사고로 이어질 수 있으니, 특히 공개 저장소에 push하기 전 `git status`로
  `.env`가 포함되지 않았는지 항상 확인하세요.

## 4. 결과물 확인 방법

실행이 끝나면 `results/` 폴더에 아래 두 파일이 생성됩니다. (파일명의 `{date}`는 입력한 `-date` 값입니다.)

- **`{date}_travel_data.json`**: 아래 구조를 가진 원본 데이터
  ```json
  {
    "date": "2026-03-15",
    "recommended": { "recommended_city": "...", "weather": "...", "events": ["..."], "reason": "..." },
    "restaurants": [ { "name": "...", "address": "...", "category": "...", "url": "...", "x": 0.0, "y": 0.0 } ],
    "errors": [ { "step": "...", "type": "...", "message": "..." } ]
  }
  ```
- **`{date}_travel_plan.md`**: 아래 섹션을 포함하는 최종 Markdown 리포트
  - 추천 지역 / 추천 이유 / 날씨 요약 / 행사·축제 / 맛집 추천(0건 시 "데이터 없음") / 1일 일정 제안 / 오류 요약(errors)

## 5. 에러 처리 정책

- **API 키 미설정**: 즉시 종료하고 설정 방법을 안내합니다.
- **지도/장소 API 실패** (네트워크/인증/쿼터/결과 0건): 맛집 섹션을 "데이터 없음"으로 처리하고 리포트 생성은 계속 진행합니다.
- **LLM JSON 파싱 실패**: 필수 키만 다시 출력하도록 프롬프트를 수정해 최대 1회 재시도합니다. 그래도 실패하면 기본값으로 대체합니다.
- **최종 리포트 생성(LLM) 실패**: 이미 확보한 데이터로 로컬에서 리포트를 조립하여 결과 파일이 항상 생성되도록 합니다.
- 모든 오류는 내부 `errors` 리스트에 `{step, type, message}` 형태로 누적되며, 원본 JSON과 최종 리포트의
  "오류 요약(errors)" 섹션에 함께 기록됩니다. 오류가 없으면 빈 리스트로 저장됩니다.

## 6. 프롬프트 수정 방법

LLM에 보내는 프롬프트 텍스트는 코드에서 분리되어 `project_config/prompts.yml`에 있습니다. 프롬프트 문구나
JSON 스키마 설명을 바꾸고 싶다면 이 파일만 수정하면 되며, 코드(`utils/prompt.py`, `utils/llm_client.py`)는
수정할 필요가 없습니다. 실행 중에도 파일 수정 시각(mtime)을 감지해 다음 호출부터 자동으로 반영됩니다.
