"""ChatGPT 커넥터(딥리서치) 호환 핸들러 — search / fetch.

search: SmartSearchService로 통합 검색 후 {"results": [{id,title,url}]} 반환
fetch : id(URI)로 전문 조회 후 {"id","title","text","url","metadata"} 반환

응답은 mcp_routes에서 content 배열에 JSON 문자열 하나로 직렬화된다
(OpenAI 규격 — format_mcp_response를 거치지 않음).
"""
import json
import logging
from urllib.parse import quote

logger = logging.getLogger("lexguard-mcp")

_LAW_GO_KR = "https://www.law.go.kr"

# search_type별 결과 리스트 키·제목 후보·fetch URI 스킴
_TYPE_CONFIG = {
    "law": {
        "list_key": "laws",
        "title_keys": ["법령명한글", "법령명", "law_name"],
        "scheme": "law",
        "link_keys": ["법령상세링크"],
    },
    "precedent": {
        "list_key": "precedents",
        "title_keys": ["사건명", "case_name"],
        "id_keys": ["사건번호", "case_number", "사건명", "case_name"],
        "scheme": "case",
        "link_keys": ["판례상세링크"],
        "extra_keys": ["법원명", "선고일자", "사건번호"],
    },
    "interpretation": {
        "list_key": "interpretations",
        "title_keys": ["안건명", "제목"],
        "scheme": "interpret",
        "link_keys": ["법령해석례상세링크"],
        "extra_keys": ["해석기관명", "회신일자"],
    },
    "administrative_appeal": {
        "list_key": "appeals",
        "title_keys": ["사건명", "재결례명"],
        "scheme": "appeal",
        "link_keys": ["행정심판례상세링크"],
        "extra_keys": ["재결일자"],
    },
    "constitutional": {
        "list_key": "decisions",
        "title_keys": ["사건명"],
        "id_keys": ["사건번호", "사건명"],
        "scheme": "constitutional",
        "extra_keys": ["종국일자"],
    },
    "committee": {
        "list_key": "decisions",
        "title_keys": ["안건명", "사건명", "제목"],
        "scheme": "committee",
    },
    "special_appeal": {
        "list_key": "appeals",
        "title_keys": ["사건명", "제목"],
        "scheme": "specialappeal",
    },
    "ordinance": {
        "list_key": "ordinances",
        "title_keys": ["자치법규명"],
        "scheme": "ordinance",
    },
    "rule": {
        "list_key": "rules",
        "title_keys": ["행정규칙명"],
        "scheme": "rule",
    },
}

# read_resource가 직접 지원하지 않는 스킴 → smart_search 강제 타입으로 폴백
_SCHEME_TO_SEARCH_TYPE = {
    "constitutional": "constitutional",
    "committee": "committee",
    "specialappeal": "special_appeal",
    "ordinance": "ordinance",
    "rule": "rule",
}

_MAX_RESULTS = 20


def _pick(item: dict, keys: list) -> str:
    for key in keys or []:
        value = item.get(key)
        if value and isinstance(value, str):
            return value.strip()
    return ""


def _item_url(item: dict, config: dict, title: str) -> str:
    link = _pick(item, config.get("link_keys", []))
    if link:
        return link if link.startswith("http") else f"{_LAW_GO_KR}{link}"
    return f"{_LAW_GO_KR}/LSW/lsSc.do?menuId=1&query={quote(title)}"


async def handle_search(arguments: dict, services: dict) -> dict:
    query = (arguments.get("query") or "").strip()
    if not query:
        return {"results": []}

    smart_search = services["smart_search"]
    try:
        raw = await smart_search.smart_search(query, max_results_per_type=5, arguments=arguments)
    except Exception as e:
        logger.error("search tool error | query=%s error=%s", query, e, exc_info=True)
        return {"results": []}

    results = []
    type_results = raw.get("results") or {}
    for search_type, type_result in type_results.items():
        config = _TYPE_CONFIG.get(search_type)
        if not config or not isinstance(type_result, dict):
            continue
        # 법령 상세 모드 (law_name 단일 결과, laws 리스트 없음)
        if search_type == "law" and type_result.get("law_name") and not type_result.get("laws"):
            law_name = type_result["law_name"]
            article = (type_result.get("article") or {}).get("article_number")
            if article:
                article = str(article).strip().lstrip("제").rstrip("조")
            doc_id = f"law://{law_name}/{article}" if article else f"law://{law_name}"
            results.append({
                "id": doc_id,
                "title": f"{law_name} 제{article}조" if article else law_name,
                "url": f"{_LAW_GO_KR}/LSW/lsSc.do?menuId=1&query={quote(law_name)}",
            })
            continue
        items = type_result.get(config["list_key"]) or []
        if not isinstance(items, list):
            items = [items]
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _pick(item, config["title_keys"])
            if not title:
                continue
            identifier = _pick(item, config.get("id_keys", [])) or title
            extras = [item.get(k) for k in config.get("extra_keys", []) if item.get(k)]
            display_title = title if not extras else f"{title} ({', '.join(str(x) for x in extras)})"
            results.append({
                "id": f"{config['scheme']}://{identifier}",
                "title": display_title,
                "url": _item_url(item, config, title),
            })
            if len(results) >= _MAX_RESULTS:
                break
        if len(results) >= _MAX_RESULTS:
            break

    logger.info("search tool | query=%s results=%d", query, len(results))
    return {"results": results}


async def handle_fetch(arguments: dict, services: dict) -> dict:
    doc_id = (arguments.get("id") or "").strip()
    if not doc_id or "://" not in doc_id:
        return {
            "id": doc_id,
            "title": doc_id,
            "text": "유효하지 않은 문서 id입니다. search 도구가 반환한 id를 그대로 사용하세요.",
            "url": _LAW_GO_KR,
            "metadata": {"error": "invalid_id"},
        }

    scheme, identifier = doc_id.split("://", 1)
    scheme = scheme.lower()
    url = f"{_LAW_GO_KR}/LSW/lsSc.do?menuId=1&query={quote(identifier.split('/', 1)[0])}"

    # read_resource가 지원하는 스킴 (law/case/interpret/appeal/lexguard)
    if scheme in ("law", "case", "interpret", "appeal", "lexguard"):
        from ..resource_handlers import read_resource
        try:
            resource = await read_resource(
                doc_id,
                services["law_detail_repo"],
                services["precedent_repo"],
                services["interpretation_repo"],
                services["appeal_repo"],
            )
        except Exception as e:
            logger.error("fetch tool error | id=%s error=%s", doc_id, e, exc_info=True)
            resource = {"error": str(e)}

        contents = resource.get("contents") or []
        text = "\n\n".join(
            c.get("text", "") for c in contents if isinstance(c, dict) and c.get("text")
        )
        if not text:
            text = resource.get("error") or "문서를 찾을 수 없습니다."
        return {
            "id": doc_id,
            "title": identifier,
            "text": text,
            "url": url,
            "metadata": {"scheme": scheme, "source": "국가법령정보센터"},
        }

    # 그 외 스킴은 smart_search 강제 타입 검색으로 폴백
    search_type = _SCHEME_TO_SEARCH_TYPE.get(scheme)
    if search_type:
        smart_search = services["smart_search"]
        try:
            raw = await smart_search.smart_search(
                identifier, search_types=[search_type], max_results_per_type=3, arguments=arguments
            )
            text = json.dumps(raw.get("results") or {}, ensure_ascii=False, indent=1)
        except Exception as e:
            logger.error("fetch fallback error | id=%s error=%s", doc_id, e, exc_info=True)
            text = f"조회 중 오류가 발생했습니다: {e}"
        return {
            "id": doc_id,
            "title": identifier,
            "text": text,
            "url": url,
            "metadata": {"scheme": scheme, "source": "국가법령정보센터"},
        }

    return {
        "id": doc_id,
        "title": identifier,
        "text": f"지원하지 않는 URI 스킴입니다: {scheme}://",
        "url": _LAW_GO_KR,
        "metadata": {"error": "unsupported_scheme"},
    }
