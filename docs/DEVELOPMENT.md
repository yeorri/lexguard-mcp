# LexGuard MCP 개발 노트 (yeorri 포크)

원본 `SeoNaRu/lexguard-mcp`를 포크해 세무 실무용으로 고친 기록이다.
다음 작업자가 이 문서만 보고 이어갈 수 있게 정리한다.

---

## 1. 운영 구성

| 용도 | 방식 | 위치 | 반영 방법 |
|---|---|---|---|
| PC (Claude 데스크톱·Code) | 로컬 stdio | `C:\Users\777la\lexguard-mcp` | Claude 완전 종료 후 재시작 |
| 모바일·웹·ChatGPT | 원격 HTTP | `https://lexguard-mcp-5du4.onrender.com/mcp` | Render 대시보드 → Manual Deploy |

- **수정 후엔 반드시 양쪽 다 반영·검증한다.** 원격은 자동 배포가 꺼져 있어 푸시만으로는 안 올라간다.
- 원격은 **Docker 런타임**이라 `render.yaml`이 아니라 `Dockerfile`로 빌드된다. 환경변수도 Dockerfile `ENV`에 둔다.
- Render 무료 플랜이라 15분 무요청 시 슬립 → 첫 호출 50초. 사용자가 손대지 않기로 함.
- 속도: 로컬이 원격보다 약 10배 빠르다(조문 5건 로컬 1.75초 / 원격 17.9초, 원격은 미국 리전 왕복).

### 로컬 등록
- Claude Code: `~/.claude.json`의 `mcpServers.lexguard`
- Claude 데스크톱 대화창: `%APPDATA%\Claude\claude_desktop_config.json`의 `mcpServers.lexguard`
- 둘 다 `".venv\Scripts\python.exe" -X utf8 C:\Users\777la\lexguard-mcp\run_stdio.py`
- **Claude 데스크톱은 MCP 설정의 `cwd`를 무시한다.** `-m src.stdio_server`로 등록하면 `No module named 'src'`로 즉사하고 로그엔 `MCP error -32000: Connection closed`만 남는다. 반드시 `run_stdio.py`를 절대경로로 지정한다.
- 권한 창이 매번 뜨지 않게 `~/.claude/settings.json`에 `"permissions.allow": ["mcp__lexguard"]`.
- 다른 PC 설치: `setup_local.ps1 -ApiKey <OC>` (venv·의존성·.env·동작검증·설정등록 일괄).

### 원격 커넥터 등록 (claude.ai·ChatGPT)
- 인증은 **"로그인 없음"**. 서버에 OAuth가 없다. 헤더도 불필요(API 키는 서버 환경변수).
- ChatGPT는 Plus 이상만 커스텀 커넥터 가능. 무료 불가. `search`/`fetch`가 딥리서치용.
- 일반 Gemini 앱은 커스텀 MCP 불가. Gemini CLI·Antigravity IDE는 가능(`~/.gemini/config/mcp_config.json`, 현재 비어 있음).

### 환경변수 (`.env`, gitignore됨)
| 키 | 값 | 비고 |
|---|---|---|
| `LAW_API_KEY` | `yeorri` | 국가법령정보센터 OC. easy-law-view와 동일 |
| `LEXGUARD_MAX_RESPONSE_BYTES` | `300000` | 응답 1회 한도(한글 약 10만 자). 기본 120000 |

---

## 2. 설계 원칙 (사용자 결정)

**MCP는 법령 API 응답을 대화 세션에 충실히 전달만 한다. 조문 구조 분석·답변 구성은 세션 몫이다.**

그래서:
- `law_article_tool`은 조립 텍스트 없이 **`원문`(API 조문단위 그대로)만** 반환한다.
  제목·시행일자·개정일자 등 원문에서 알 수 있는 값은 서버가 따로 뽑지 않는다.
  (조립 규칙은 예외가 끝없이 나와 틀리면 답이 통째로 틀어진다. 실제로 상증법 제53조 두문이 사라진 사고가 있었다.)
- 조립 로직(`_render_article_text`)은 텍스트가 계약인 `fetch`·resources에서만 쓴다.
- 도구 설명·응답에 답변 형식 지시를 넣지 않는다("조문 전체 인용 금지" 같은 원본 지시문 제거함).
  예외: `document_issue_tool`은 검토 산출물 규격이라 남겨둠.
- `structuredContent` 사용 안 함(content와 100% 중복이라 응답이 두 배였음). `outputSchema`도 광고 안 함.
- 값이 null인 필드는 응답에 싣지 않는다.

---

## 3. 국가법령정보 DRF API — 알아낸 것

### 응답 키가 target마다 제각각 (하드코딩 금지)
`src/utils/drf_parse.py`의 `parse_drf_list`가 대소문자 무시·2단 중첩까지 탐색한다.

| target | wrapper | 데이터 키 |
|---|---|---|
| prec 판례 | PrecSearch | prec |
| detc 헌재 | DetcSearch | **Detc** |
| expc 해석례 | **Expc** | expc |
| *CgmExpc 부처해석 | CgmExpc | cgmExpc |
| admrul 행정규칙 | **AdmRul**Search | admrul (1건이면 dict) |
| decc 행정심판 | Decc | decc |
| ordin 자치법규 | OrdinSearch | **law** |
| trty 조약 | TrtySearch | **Trty** |
| elaw·lsAbrv·delHst | LawSearch | **law** |
| oneview | items | **item** |
| 위원회(ppc 등) | Ppc/Ftc/… | target명 |

### 엔드포인트·파라미터 함정
- 용어 연계(`lstrmRlt`·`dlytrmRlt`·`lstrmRltJo`)는 **lawService.do**. lawSearch.do로 부르면 빈 응답.
- 관련법령(`lsRlt`)은 query가 아니라 **ID(법령ID)**.
- `law` target은 **법령 이름만** 검색한다. 문장형 질의는 0건 → `search` 도구는 `aiSearch`로 폴백.
- 조문 조회: `eflawjosub`가 메타만 주는 조문이 있어 법령 전체(`target=law&MST=`)를 받아 조문단위를 찾는다. 소득세법 시행령 전체 응답은 약 3MB.
- 조문번호 JO는 6자리(`015603` = 제156조의3). 가지번호 구분자로 `의`·`-`·`.`·`_` 모두 인식.
- 약칭 API(`lsAbrv`)는 검색어를 무시하고 전체 목록만 줘서 못 쓴다 → `BaseLawRepository.LAW_NAME_ALIASES`로 직접 매핑(조특법·상증법·부가법 등).

### 이 인증키로 안 되는 것
- **이력 API**(`lsHstInf`·`lsJoHstInf`): 파라미터 무관 항상 totalCnt=0 (인증 오류 아님). 신청 목록에 '이력' 항목 없음.
- **연혁 본문**(`lsHistory`): JSON 미지원, HTML만.
- 국세청·재정경제부 법령해석: 목록만 제공, 본문 API 없음.
- **대안**: `eflaw`가 시행일자별 버전을 MST와 함께 준다(조특법 750건).
  → `law_history_tool(search_type="version_list")`로 MST를 얻어 `law_article_tool(law_id=<MST>)`로 과거 조문을 열고 대조한다.

### 미해결
- 감사원 사전컨설팅 의견서: target 코드 미확인(후보 16개 빈 응답)
- 조문→법령용어 연계(`joRltLstrm`): target은 있으나 파라미터 조합 미확인. 반대 방향(용어→조문)은 정상.
- 이 둘은 open.law.go.kr 각 API 상세 가이드의 요청 URL 예시가 있으면 바로 붙일 수 있다.

---

## 4. 도구 (23종)

원본 18종에 추가: `search`·`fetch`(ChatGPT 규격), `legal_term_tool`(법령용어·일상용어·연계),
`ai_search_tool`(지능형 검색·관련법령), `school_rule_tool`(학칙·공단).

- `ai_search_tool`·`legal_term_tool`의 `operation`은 선택. 생략·영문 표현도 받는다(생략 시 필수로 막아 가장 흔한 호출이 실패했었음).
- `fetch`는 `law://`·`rule://`·`case://`·`interpret://`·`appeal://` 지원. `rule://<행정규칙일련번호>`로 고시 본문 조회.
- 없는 조문·항을 요청하면 `ARTICLE_NOT_FOUND`·`SUBSECTION_NOT_FOUND` 오류(예전엔 조 제목만 담아 success로 보고했음).

---

## 5. 응답 크기

- 한도 `LEXGUARD_MAX_RESPONSE_BYTES` (한글 1자 = 3바이트 주의). 최장 조문(소령 제167조의3, 원문 16,806자)도 한도 안.
- 한도는 **호출 1회당**이다. 여러 조문 검토는 여러 번 호출하면 되므로 무관.
- 초과 시 목록을 이진 탐색으로 한도까지 채워 자르고 `_truncation_note`로 page·범위 축소 안내.
- 크기 제한은 **포맷 변환 뒤**에 적용해야 한다(예전엔 변환 전에 불러 한 번도 적용 안 됐음 → 468KB 응답).
- 4분 타임아웃은 클라이언트 쪽 한계다. 우리 코드의 타임아웃은 DRF 호출 10초뿐.

---

## 6. 주요 버그 이력 (재발 방지용)

| 증상 | 원인 |
|---|---|
| 해석례·예규·행정규칙·위원회가 늘 0건 | DRF 응답 키 하드코딩 |
| 긴 조문이 500자로 잘림 | 24KB 한도 + 1KB 초과 문자열 절단 |
| 상증법 §53 두문 누락 | 항이 있으면 조문내용을 버리는 조립 규칙 |
| `156-3`이 제156조를 반환 | 가지번호 구분자를 `의`만 인식 |
| fetch 직렬화 오류 | `api_url`에 httpx.URL 객체 (12개 파일 44곳) |
| 과거 조문 조회 불가 | 핸들러가 `law_id`를 버리고 None 전달 |
| 동시 호출이 밀림 | stdio 루프가 요청을 직렬 처리 (태스크 병렬화로 수정) |
| search URL에 API 키 노출 | DRF 상세링크의 `OC=` 그대로 사용 |

---

## 7. 개발·검증 팁

- 로컬 검증: `run_stdio.py`에 JSON-RPC 줄을 stdin으로 넣으면 된다 (Claude 재시작 불필요).
- 원격과 같은 실행 경로 검증: `uvicorn src.main:api` (Docker CMD와 동일).
- **Git Bash의 curl은 한글을 cp949로 보내 0건이 나온다.** 한글 질의 테스트는 Python(UTF-8)으로.
- PowerShell 5.1: `.ps1`은 UTF-8 **BOM** 필요, `Get-Content`는 `-Encoding UTF8` 필요, native exe stderr를 `2>`로 받지 말 것.
- 데스크톱 로그: `%APPDATA%\Claude\logs\mcp-server-lexguard.log` (요청·응답 id가 남음). 2026-08-21 이후 로그 기록이 멈춘 상태 — 원인 미확인, 앱 쪽 문제로 보임.
- 테스트: `.venv\Scripts\python.exe -m pytest tests -q` (406개).
