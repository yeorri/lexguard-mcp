"""ChatGPT 커넥터(딥리서치) 호환 도구 스키마 — search / fetch.

OpenAI MCP 커넥터 규격:
  search(query)  → {"results": [{"id", "title", "url"}]}
  fetch(id)      → {"id", "title", "text", "url", "metadata"}

두 도구의 응답은 content 배열에 JSON 문자열 하나로 직렬화해야 하므로
mcp_routes에서 format_mcp_response를 거치지 않고 직접 포맷한다.
"""

SCHEMAS = [
    {
        "name": "search",
        "description": (
            "한국 법령·판례·법령해석·행정심판을 통합 검색합니다. "
            "질의를 분석해 적절한 검색 유형을 자동 선택하고, "
            "각 결과의 id는 fetch 도구로 전문을 조회할 수 있는 URI입니다. "
            "예: '부당해고 판례', '근로기준법 제23조', '개인정보보호법 해석'"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색어 (법령명, 조문, 판례 키워드, 법률 질문 등)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch",
        "description": (
            "search 결과의 id(URI)로 문서 전문을 조회합니다. "
            "지원 URI: law://법령명, law://법령명/조문번호, "
            "case://검색어, interpret://검색어, appeal://검색어"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "search 결과에서 받은 문서 id (예: law://근로기준법/23)"
                }
            },
            "required": ["id"]
        }
    },
]
