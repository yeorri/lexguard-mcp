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

응답 구성:
- content: 제목·두문·항·호를 순서대로 이어붙인 텍스트
- 원문: 국가법령정보센터가 준 조문단위 원본(조립 결과가 의심스러우면 대조용)
- 조문시행일자·제개정일자·개정일자·삭제일자: 개정 시점 확인용""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "law_name": {
                    "type": "string",
                    "description": "법령명 (예: 근로기준법, 민법, 형법, 개인정보보호법)"
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
