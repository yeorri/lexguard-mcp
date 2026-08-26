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
    # DRF 상세링크에는 OC(API 키)가 쿼리로 붙어 있다. 그대로 노출하면 키가
    # 모델 응답·클라이언트 로그에 남으므로 공개 검색 URL로 대체한다.
    if link and "/DRF/" not in link and "OC=" not in link:
        return link if link.startswith("http") else f"{_LAW_GO_KR}{link}"
    return f"{_LAW_GO_KR}/LSW/lsSc.do?menuId=1&query={quote(title)}"


async def _ai_search_fallback(query: str, services: dict, arguments: dict) -> list:
    """지능형 법령검색(aiSearch)으로 조문을 찾는다.

    DRF의 law 타입은 '법령 이름'만 검색하므로 '1세대 3주택 중과' 같은
    문장형 질의에는 아무것도 걸리지 않는다. ChatGPT 딥리서치처럼
    자연어로 물어오는 경우가 많아 의미 기반 검색으로 보완한다.
    """
    repo = services.get("legal_term_repo")
    if repo is None:
        return []
    try:
        res = await repo.ai_search(query, 1, 10, arguments)
    except Exception as e:
        logger.error("search fallback error | query=%s error=%s", query, e, exc_info=True)
        return []

    results = []
    for item in (res.get("articles") or []):
        if not isinstance(item, dict):
            continue
        law_name = (item.get("법령명") or "").strip()
        if not law_name:
            continue
        try:
            article = int(item.get("조문번호") or 0)
        except (TypeError, ValueError):
            article = 0
        try:
            branch = int(item.get("조문가지번호") or 0)
        except (TypeError, ValueError):
            branch = 0

        if article:
            ref = f"{article}의{branch}" if branch else str(article)
            doc_id = f"law://{law_name}/{ref}"
            label = f"제{article}조의{branch}" if branch else f"제{article}조"
        else:
            doc_id = f"law://{law_name}"
            label = ""

        body = (item.get("조문내용") or "").strip().replace("\n", " ")
        title = f"{law_name} {label}".strip()
        if body:
            title = f"{title} — {body[:60]}"
        results.append({
            "id": doc_id,
            "title": title,
            "url": f"{_LAW_GO_KR}/LSW/lsSc.do?menuId=1&query={quote(law_name)}",
        })
        if len(results) >= _MAX_RESULTS:
            break
    return results


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

    if not results:
        # 법령명 검색으로 안 걸리는 문장형 질의는 의미 기반 검색으로 보완
        results = await _ai_search_fallback(query, services, arguments)
        logger.info("search tool | query=%s fallback=aiSearch results=%d", query, len(results))
    else:
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
