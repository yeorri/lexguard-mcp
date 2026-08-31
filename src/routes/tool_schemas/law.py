"""법령 직접 조회 도구 스키마: law_article_tool, law_comparison_tool."""

SCHEMAS = [
    {
        "name": "law_article_tool",
        "priority": 1,
        "category": "law",
        "description": """특정 법령의 조문을 직접 정밀 조회합니다. 법령명과 조문번호를 알고 있을 때 사용하세요.
법령 신구·연혁·3단 비교가 필요하면 law_comparison_tool을 사용하세요.

조문번호는 '95', '제95조', 가지번호는 '167의3'(또는 167-3) 형식으로 지정합니다.
hang·ho·mok을 지정하면 해당 부분만, 생략하면 조 전체를 반환합니다.

과거 시점 조문이 필요하면 law_history_tool(search_type=version_list)로
그 시점의 법령일련번호(MST)를 얻어 law_id에 넘기세요.

응답 구성:
- 원문: 국가법령정보센터가 준 조문단위 원본. 조문내용(두문)과 항·호·목이
  구조 그대로 들어 있으니 여기서 필요한 부분을 읽으세요.
- law_id: 조회에 쓰인 법령일련번호(MST). 다른 시점 조회에 재사용할 수 있습니다.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "law_name": {
                    "type": "string",
                    "description": "법령명 (예: 근로기준법, 민법, 형법, 개인정보보호법)"
                },
                "law_id": {
                    "type": "string",
                    "description": "법령일련번호(MST). 특정 시점 버전을 조회할 때 사용합니다. "
                                   "law_history_tool(search_type=version_list)로 얻습니다."
                },
                "article_number": {
                    "type": "string",
                    "description": "조문 번호 (예: '50', '2', '110'). 생략 시 법령 전체 개요 반환"
                },
                "hang": {"type": "string", "description": "항 번호 (예: '1', '2')"},
                "ho": {"type": "string", "description": "호 번호 (예: '1', '2')"},
                "mok": {"type": "string", "description": "목 번호 (예: '가', '나')"}
            },
            "required": ["law_name"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "law_name": {"type": "string"},
                "article_number": {"type": ["string", "null"]},
                "law_id": {"type": ["string", "null"]},
                "detail": {"type": ["object", "null"]},
                "error": {"type": ["string", "null"]}
            }
        }
    },
    {
        "name": "law_comparison_tool",
        "priority": 1,
        "category": "law",
        "description": """국가법령정보센터 API 기준으로 법령 신구·연혁·3단 비교 결과를 조회합니다. 비교·연혁 조회가 목적일 때 사용하세요. 일반 법률 질문·판례 검색은 legal_qa_tool 또는 전용 툴을 쓰세요.

이 도구는 국가법령정보센터 조회 결과를 그대로 전달합니다.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "law_name": {
                    "type": "string",
                    "description": "비교할 법령명 (예: 형법, 민법, 근로기준법)",
                },
                "compare_type": {
                    "type": "string",
                    "description": "비교 유형: 신구법(신·구법 대비), 연혁(법령 연혁), 3단비교. 사용자 문구에 연혁/3단비교/신구법이 있으면 그 값을 그대로 넣으세요. 생략 시 기본값은 신구법입니다.",
                    "enum": ["신구법", "연혁", "3단비교"],
                    "default": "신구법",
                },
            },
            "required": ["law_name"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "law_name": {"type": "string"},
                "law_id": {"type": ["string", "null"]},
                "compare_type": {"type": "string"},
                "comparison": {"type": "object"},
                "error": {"type": ["string", "null"]},
                "error_code": {"type": ["string", "null"]},
                "recovery_guide": {"type": ["string", "null"]},
            },
        },
    },
]
