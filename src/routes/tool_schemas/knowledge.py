"""지식베이스 계열 도구 스키마: 법령용어·용어 연계·지능형 검색·학칙공단."""
from ._common import DISCLAIMER

# 용어 계열 operation → (저장소 메서드명, 입력 성격)
TERM_OPERATIONS = [
    "법령용어",
    "지식베이스용어",
    "일상용어",
    "용어-일상용어연계",
    "일상용어-용어연계",
    "용어-조문연계",
]

AI_OPERATIONS = ["조문검색", "연관법령", "관련법령"]

SCHEMAS = [
    {
        "name": "legal_term_tool",
        "priority": 3,
        "category": "term",
        "description": f"""법령용어·일상용어를 조회하고 용어 간·용어-조문 연계를 확인합니다.

operation 선택:
- 법령용어: 법령에서 정의된 용어 검색 (target=lstrm)
- 지식베이스용어: 지능형 지식베이스의 법령용어 (target=lstrmAI)
- 일상용어: 법령용어에 대응하는 일상용어 (target=dlytrm)
- 용어-일상용어연계: 법령용어에 연결된 일상용어 목록 (상위어·하위어 관계 포함)
- 일상용어-용어연계: 일상용어에 연결된 법령용어 목록
- 용어-조문연계: 그 용어가 실제로 쓰인 법령 조문 목록

일상 표현만 아는 상태에서 정확한 법령용어를 찾거나, 특정 용어가 어느 조문에
쓰이는지 확인할 때 사용하세요.

{DISCLAIMER}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": TERM_OPERATIONS,
                    "description": "조회 유형",
                },
                "query": {"type": "string", "description": "검색할 용어 (예: 양도, 소득, 임대차)"},
                "page": {"type": "integer", "default": 1, "minimum": 1},
                "per_page": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["operation", "query"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "terms": {"type": "array"},
                "articles": {"type": "array"},
                "links": {"type": "array"},
                "error": {"type": "string"},
            },
        },
    },
    {
        "name": "ai_search_tool",
        "priority": 3,
        "category": "search",
        "description": f"""국가법령정보센터의 지능형 법령검색으로 질의와 의미가 가까운 조문을 찾습니다.

operation 선택:
- 조문검색: 자연어 질의로 관련 법령 조문 검색 (target=aiSearch)
- 연관법령: 질의와 연관된 법령 목록 (target=aiRltLs)
- 관련법령: 특정 법령의 관련법령 조회. query 대신 law_id(법령ID)가 필요합니다.

키워드가 정확히 일치하지 않아도 의미 기반으로 찾으므로, 조문 번호를 모르는
상태에서 상황만 알 때 유용합니다.

{DISCLAIMER}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": AI_OPERATIONS,
                    "description": "조회 유형",
                },
                "query": {"type": "string", "description": "자연어 질의 (조문검색·연관법령에 사용)"},
                "law_id": {"type": "string", "description": "법령ID (관련법령에만 사용, 예: 001766)"},
                "page": {"type": "integer", "default": 1, "minimum": 1},
                "per_page": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["operation"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "articles": {"type": "array"},
                "related_laws": {"type": "array"},
                "error": {"type": "string"},
            },
        },
    },
    {
        "name": "school_rule_tool",
        "priority": 4,
        "category": "rule",
        "description": f"""학칙·공단·공공기관의 자체 규정을 검색합니다 (target=school).

대학 학칙, 공단·공공기관 내부 규정이 대상입니다. 법령·행정규칙과는 별도 체계이므로
기관 내부 규정을 확인할 때만 사용하세요.

{DISCLAIMER}""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "규정명 또는 기관명 검색어"},
                "page": {"type": "integer", "default": 1, "minimum": 1},
                "per_page": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "rules": {"type": "array"},
                "error": {"type": "string"},
            },
        },
    },
]
