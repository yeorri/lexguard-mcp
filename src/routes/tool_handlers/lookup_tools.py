"""전용 조회 도구 핸들러 (law_article, law_comparison, 각종 lookup)."""
import logging
from ...utils.mcp_tool_args import resolve_law_comparison_tool

logger = logging.getLogger("lexguard-mcp")


async def handle_law_article(arguments: dict, services: dict) -> dict:
    law_name = arguments.get("law_name")
    # 법령일련번호(MST)를 주면 그 시점 버전의 조문을 조회한다.
    # law_history_tool(version_list)로 과거 MST를 얻어 개정 전후를 대조할 때 쓴다.
    law_id = arguments.get("law_id") or arguments.get("mst")
    article_number = arguments.get("article_number")
    hang = arguments.get("hang")
    ho = arguments.get("ho")
    mok = arguments.get("mok")

    if not law_name and not law_id:
        return {
            "error": "law_name 또는 law_id 중 하나가 필요합니다.",
            "recovery_guide": "법령명을 지정하거나, 특정 시점 버전을 볼 때는 "
                              "law_history_tool(search_type=version_list)로 얻은 "
                              "법령일련번호를 law_id로 넘기세요.",
        }

    mode = "single" if article_number else "detail"
    logger.debug(
        "Calling law_article_tool | law=%s law_id=%s article=%s hang=%s ho=%s mok=%s",
        law_name, law_id, article_number, hang, ho, mok,
    )
    return await services["law_detail_repo"].get_law(
        law_id, law_name, mode, article_number, hang, ho, mok, arguments,
    )


async def handle_law_comparison(arguments: dict, services: dict) -> dict:
    req_cmp, err_cmp = resolve_law_comparison_tool(arguments)
    if err_cmp:
        return err_cmp
    return await services["law_comparison"].compare_laws(req_cmp, arguments)


async def handle_precedent_lookup(arguments: dict, services: dict) -> dict:
    return await services["smart_search"].precedent_lookup(
        keyword=arguments.get("keyword"),
        case_number=arguments.get("case_number"),
        page=int(arguments.get("page", 1)),
        per_page=int(arguments.get("per_page", 10)),
        court=arguments.get("court"),
        date_from=arguments.get("date_from"),
        date_to=arguments.get("date_to"),
        arguments=arguments,
    )


async def handle_interpretation(arguments: dict, services: dict) -> dict:
    return await services["smart_search"].interpretation_lookup(
        query=arguments.get("query", ""),
        page=int(arguments.get("page", 1)),
        per_page=int(arguments.get("per_page", 10)),
        agency=arguments.get("agency"),
        arguments=arguments,
    )


async def handle_administrative_appeal(arguments: dict, services: dict) -> dict:
    return await services["smart_search"].administrative_appeal_lookup(
        query=arguments.get("query", ""),
        page=int(arguments.get("page", 1)),
        per_page=int(arguments.get("per_page", 10)),
        date_from=arguments.get("date_from"),
        date_to=arguments.get("date_to"),
        arguments=arguments,
    )


async def handle_constitutional_decision(arguments: dict, services: dict) -> dict:
    return await services["smart_search"].constitutional_decision_lookup(
        query=arguments.get("query", ""),
        page=int(arguments.get("page", 1)),
        per_page=int(arguments.get("per_page", 10)),
        date_from=arguments.get("date_from"),
        date_to=arguments.get("date_to"),
        arguments=arguments,
    )


async def handle_committee_decision(arguments: dict, services: dict) -> dict:
    return await services["smart_search"].committee_decision_lookup(
        committee_type=arguments.get("committee_type", ""),
        query=arguments.get("query", ""),
        page=int(arguments.get("page", 1)),
        per_page=int(arguments.get("per_page", 10)),
        arguments=arguments,
    )


async def handle_special_administrative_appeal(arguments: dict, services: dict) -> dict:
    return await services["smart_search"].special_administrative_appeal_lookup(
        tribunal_type=arguments.get("tribunal_type", ""),
        query=arguments.get("query", ""),
        page=int(arguments.get("page", 1)),
        per_page=int(arguments.get("per_page", 10)),
        arguments=arguments,
    )


async def handle_local_ordinance(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    return await services["smart_search"].local_ordinance_lookup(
        query=arguments.get("query"),
        local_government=arguments.get("local_government"),
        sub_local_government=arguments.get("sub_local_government"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )


async def handle_administrative_rule(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    return await services["smart_search"].administrative_rule_lookup(
        query=arguments.get("query"),
        agency=arguments.get("agency"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )


async def handle_ministry_interpretation(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    return await services["smart_search"].ministry_interpretation_lookup(
        query=arguments.get("query"),
        agency=arguments.get("agency"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )


async def handle_law_history(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    search_type = arguments.get("search_type", "law_change")

    # 이력 계열 API(lsHstInf·lsJoHstInf)는 이 인증키로 항상 0건이고
    # 연혁 본문(lsHistory)은 HTML만 준다. 대신 eflaw가 시행일자별 버전을
    # MST와 함께 주므로, 그 MST로 과거 조문을 열어 개정 시점을 확정할 수 있다.
    if search_type in ("version_list", "버전목록", "시행일목록"):
        repo = services.get("law_history_repo")
        if repo is None:
            return {"error": "버전 목록 조회를 사용할 수 없습니다."}
        return await repo.list_law_versions(
            law_name=arguments.get("query") or arguments.get("law_name"),
            page=int(arguments.get("page", 1)),
            per_page=max(1, min(100, int(arguments.get("per_page", 50)))),
            arguments=arguments,
        )

    return await services["smart_search"].law_history_lookup(
        search_type=arguments.get("search_type", "law_change"),
        query=arguments.get("query"),
        law_id=arguments.get("law_id"),
        article_number=arguments.get("article_number"),
        date=arguments.get("date"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )


async def handle_law_info(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    return await services["smart_search"].law_info_lookup(
        info_type=arguments.get("info_type", "english_law"),
        query=arguments.get("query"),
        item_id=arguments.get("item_id"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )


async def handle_law_form(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    return await services["smart_search"].law_form_lookup(
        form_type=arguments.get("form_type", "law"),
        query=arguments.get("query"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )


async def handle_law_link(arguments: dict, services: dict) -> dict:
    per_page = max(1, min(50, int(arguments.get("per_page", 20))))
    return await services["smart_search"].law_link_lookup(
        link_type=arguments.get("link_type", "law_to_ordinance"),
        query=arguments.get("query"),
        law_id=arguments.get("law_id"),
        department=arguments.get("department"),
        region_code=arguments.get("region_code"),
        page=int(arguments.get("page", 1)),
        per_page=per_page,
        arguments=arguments,
    )
