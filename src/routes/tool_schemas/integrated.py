"""통합 도구 스키마: legal_qa_tool, document_issue_tool."""
from ...utils.document_issue_prompts import DOCUMENT_ISSUE_TOOL_DESCRIPTION_TEXT

SCHEMAS = [
    {
        "name": "legal_qa_tool",
        "priority": 1,
        "category": "integrated",
        "description": """법률 질문에 대한 법적 근거의 실마리를 제공합니다. 법령, 판례, 행정해석, 위원회 결정례 등을 통합 검색합니다.
통합 법률 검색·근거 실마리의 기본 진입점입니다. 출처가 한정된 검색(판례만, 해석만, 심판만 등)은 해당 전용 툴을 우선 검토하세요.

검색 타입(법령·판례·해석·심판 등)은 질의를 분석해 자동 선택되며,
results 객체에 타입별 결과가 담깁니다.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "사용자의 법률 질문 (예: '프리랜서 근로자성 판례', '최근 5년 부당해고 판례', '개인정보보호법 해석')"
                },
                "max_results_per_type": {
                    "type": "integer",
                    "description": "타입당 최대 결과 수",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["query"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "success_transport": {"type": "boolean"},
                "success_search": {"type": "boolean"},
                "has_legal_basis": {"type": "boolean"},
                "query": {"type": "string"},
                "domain": {"type": "string"},
                "detected_intent": {"type": "string"},
                "results": {"type": "object"},
                "sources_count": {"type": "object"},
                "total_sources": {"type": "integer"},
                "missing_reason": {"type": ["string", "null"]},
                "elapsed_seconds": {"type": "number"},
                "pipeline_version": {"type": "string"}
            }
        }
    },
    {
        "name": "document_issue_tool",
        "priority": 1,
        "category": "document",
        "description": DOCUMENT_ISSUE_TOOL_DESCRIPTION_TEXT,
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_text": {
                    "type": "string",
                    "description": "계약서/약관 등 문서 텍스트"
                },
                "auto_search": {
                    "type": "boolean",
                    "description": "조항별 추천 검색어로 자동 검색 수행 여부",
                    "default": True
                },
                "max_clauses": {
                    "type": "integer",
                    "description": "자동 검색할 조항 수 제한",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10
                },
                "max_results_per_type": {
                    "type": "integer",
                    "description": "타입당 최대 결과 수",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["document_text"]
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "success_transport": {"type": "boolean"},
                "success_search": {"type": "boolean"},
                "auto_search": {"type": "boolean"},
                "analysis_success": {"type": "boolean"},
                "has_legal_basis": {"type": "boolean"},
                "document_analysis": {"type": "object"},
                "evidence_results": {"type": "array"},
                "missing_reason": {"type": ["string", "null"]},
                "legal_basis_block": {"type": "object"}
            }
        }
    },
]
