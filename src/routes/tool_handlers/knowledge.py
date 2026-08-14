"""지식베이스 계열 도구 핸들러: 법령용어·용어 연계·지능형 검색·학칙공단."""
import logging

logger = logging.getLogger("lexguard-mcp")

# operation을 생략하거나 다른 표현으로 보내는 호출이 흔하다.
# 필수로 막으면 가장 자연스러운 호출(query만 전달)이 그대로 실패한다.
_TERM_ALIASES = {
    "법령용어": "법령용어", "term": "법령용어", "용어": "법령용어",
    "지식베이스용어": "지식베이스용어", "kb": "지식베이스용어", "lstrmai": "지식베이스용어",
    "일상용어": "일상용어", "daily": "일상용어", "dlytrm": "일상용어",
    "용어-일상용어연계": "용어-일상용어연계", "용어→일상용어": "용어-일상용어연계",
    "일상용어-용어연계": "일상용어-용어연계", "일상용어→용어": "일상용어-용어연계",
    "용어-조문연계": "용어-조문연계", "용어→조문": "용어-조문연계", "조문연계": "용어-조문연계",
}

_AI_ALIASES = {
    "조문검색": "조문검색", "search": "조문검색", "검색": "조문검색",
    "법령검색": "조문검색", "aisearch": "조문검색",
    "연관법령": "연관법령", "related": "연관법령", "airltls": "연관법령",
    "관련법령": "관련법령", "lsrlt": "관련법령", "related_laws": "관련법령",
}


def _normalize(value, aliases: dict, default: str) -> str:
    """operation 값을 표준 명칭으로 바꾼다. 없거나 모르면 기본값."""
    if not value:
        return default
    key = str(value).strip().lower().replace(" ", "").replace("_", "")
    return aliases.get(key) or aliases.get(str(value).strip()) or default


async def handle_legal_term(arguments: dict, services: dict) -> dict:
    repo = services["legal_term_repo"]
    operation = _normalize(arguments.get("operation"), _TERM_ALIASES, "법령용어")
    query = (arguments.get("query") or "").strip()
    page = int(arguments.get("page", 1))
    per_page = int(arguments.get("per_page", 20))

    if not query:
        return {
            "error": "query가 필요합니다.",
            "recovery_guide": "검색할 용어를 입력하세요 (예: 양도, 소득).",
        }

    logger.debug("legal_term_tool | operation=%s query=%s", operation, query)

    if operation == "법령용어":
        return await repo.search_legal_term(query, page, per_page, arguments)
    if operation == "지식베이스용어":
        return await repo.search_kb_legal_term(query, page, per_page, arguments)
    if operation == "일상용어":
        return await repo.search_daily_term(query, page, per_page, arguments)
    if operation == "용어-일상용어연계":
        return await repo.link_term_to_daily(query, arguments)
    if operation == "일상용어-용어연계":
        return await repo.link_daily_to_term(query, arguments)
    if operation == "용어-조문연계":
        return await repo.link_term_to_article(query, arguments)

    return {
        "error": f"지원하지 않는 operation입니다: {operation}",
        "recovery_guide": "법령용어 / 지식베이스용어 / 일상용어 / 용어-일상용어연계 / 일상용어-용어연계 / 용어-조문연계 중 하나를 사용하세요.",
    }


async def handle_ai_search(arguments: dict, services: dict) -> dict:
    repo = services["legal_term_repo"]
    raw_op = arguments.get("operation")
    # law_id만 주고 operation을 생략하면 관련법령 조회 의도로 본다.
    default_op = "관련법령" if (not raw_op and arguments.get("law_id")) else "조문검색"
    operation = _normalize(raw_op, _AI_ALIASES, default_op)
    query = (arguments.get("query") or "").strip()
    page = int(arguments.get("page", 1))
    per_page = int(arguments.get("per_page", 20))

    logger.debug("ai_search_tool | operation=%s query=%s", operation, query)

    if operation == "관련법령":
        law_id = (arguments.get("law_id") or "").strip()
        if not law_id:
            return {
                "error": "관련법령 조회에는 law_id(법령ID)가 필요합니다.",
                "recovery_guide": "law_article_tool 등으로 먼저 법령ID를 확인한 뒤 지정하세요.",
            }
        return await repo.search_related_laws(law_id, arguments)

    if not query:
        return {
            "error": "query가 필요합니다.",
            "recovery_guide": "찾고자 하는 내용을 자연어로 입력하세요.",
        }

    if operation == "조문검색":
        return await repo.ai_search(query, page, per_page, arguments)
    if operation == "연관법령":
        return await repo.ai_related_laws(query, page, per_page, arguments)

    return {
        "error": f"지원하지 않는 operation입니다: {operation}",
        "recovery_guide": "조문검색 / 연관법령 / 관련법령 중 하나를 사용하세요.",
    }


async def handle_school_rule(arguments: dict, services: dict) -> dict:
    repo = services["legal_term_repo"]
    return await repo.search_school_rule(
        (arguments.get("query") or "").strip() or None,
        int(arguments.get("page", 1)),
        int(arguments.get("per_page", 20)),
        arguments,
    )
