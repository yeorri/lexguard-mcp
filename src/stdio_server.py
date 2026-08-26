#!/usr/bin/env python3
"""
LexGuard MCP — stdio 전송 진입점.

Claude Desktop / Claude Code 등이 이 프로세스를 직접 실행하고
stdin/stdout으로 JSON-RPC 2.0 메시지를 주고받는다. 네트워크를 타지 않으므로
원격 URL 방식처럼 연결이 끊길 일이 없다.

실행:
    python -m src.stdio_server

stdout은 JSON-RPC 메시지 전용이다. 로그·경고는 모두 stderr로 보낸다.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 프로세스 cwd가 어디든 저장소의 .env를 읽도록 절대경로로 로드
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

# stdout 오염 방지: 라이브러리가 print()로 stdout에 쓰더라도 stderr로 흘려보내고,
# JSON-RPC 응답은 아래 _STDOUT 핸들로만 기록한다.
_STDOUT = sys.stdout
sys.stdout = sys.stderr

from .config.settings import setup_logging  # noqa: E402
from .services.health_service import HealthService  # noqa: E402
from .services.law_comparison_service import LawComparisonService  # noqa: E402
from .services.smart_search_service import SmartSearchService  # noqa: E402
from .services.situation_guidance_service import SituationGuidanceService  # noqa: E402
from .repositories.law_detail import LawDetailRepository  # noqa: E402
from .repositories.precedent_repository import PrecedentRepository  # noqa: E402
from .repositories.law_interpretation_repository import LawInterpretationRepository  # noqa: E402
from .repositories.administrative_appeal_repository import AdministrativeAppealRepository  # noqa: E402
from .repositories.legal_term_repository import LegalTermRepository  # noqa: E402
from .repositories.administrative_rule_repository import AdministrativeRuleRepository  # noqa: E402
from .routes.mcp_routes import _build_prompts_list, _get_prompt  # noqa: E402
from .routes.resource_handlers import build_resources_list, read_resource  # noqa: E402
from .routes.tool_handlers import dispatch  # noqa: E402
from .routes.tool_schemas import TOOLS_LIST  # noqa: E402
from .utils.response_formatter import format_mcp_response, sanitize_for_mcp_json  # noqa: E402
from .utils.response_truncator import shrink_response_bytes  # noqa: E402

logger = setup_logging()

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "lexguard-mcp"

_health_service = HealthService()
_smart_search_service = SmartSearchService()
_situation_guidance_service = SituationGuidanceService()
_law_comparison_service = LawComparisonService()
_law_detail_repo = LawDetailRepository()
_precedent_repo = PrecedentRepository()
_interpretation_repo = LawInterpretationRepository()
_appeal_repo = AdministrativeAppealRepository()
_legal_term_repo = LegalTermRepository()
_admin_rule_repo = AdministrativeRuleRepository()

_SERVICES = {
    "health": _health_service,
    "smart_search": _smart_search_service,
    "situation_guidance": _situation_guidance_service,
    "law_comparison": _law_comparison_service,
    "law_detail_repo": _law_detail_repo,
    "precedent_repo": _precedent_repo,
    "interpretation_repo": _interpretation_repo,
    "appeal_repo": _appeal_repo,
    "legal_term_repo": _legal_term_repo,
    "admin_rule_repo": _admin_rule_repo,
}


def _server_version() -> str:
    try:
        from importlib.metadata import version as pkg_version

        return pkg_version("lexguard-mcp")
    except Exception:
        return "1.0.0"


def _mcp_tools() -> list:
    """tools/list 응답용으로 MCP 표준 필드만 남긴다 (mcp_routes와 동일 규칙)."""
    tools = []
    for tool in TOOLS_LIST:
        annotations = {}
        if "priority" in tool:
            annotations["priority"] = tool.get("priority")
        if "category" in tool:
            annotations["category"] = tool.get("category")
        filtered = {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"),
            "outputSchema": tool.get("outputSchema"),
        }
        filtered = {k: v for k, v in filtered.items() if v is not None}
        if annotations:
            filtered["annotations"] = annotations
        tools.append(filtered)
    return tools


async def _call_tool(tool_name: str, arguments: dict) -> dict:
    try:
        result = await dispatch(tool_name, arguments, _SERVICES)
    except Exception as e:
        logger.error("Tool call error | tool=%s error=%s", tool_name, e, exc_info=True)
        result = {"error": str(e)}

    if not result:
        result = {"error": "Tool returned no result"}

    result = sanitize_for_mcp_json(result)

    if tool_name in ("search", "fetch"):
        # ChatGPT 커넥터 규격: content에 JSON 문자열 하나만
        formatted = {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]
        }
    else:
        formatted = format_mcp_response(result, tool_name)

    # 크기 제한은 MCP 포맷으로 변환한 뒤에 적용해야 한다.
    # shrink_response_bytes는 structuredContent가 있을 때만 축소하는데,
    # 그 키는 format_mcp_response가 만든다. 변환 전에 부르면 무조건 무효였다.
    return shrink_response_bytes(formatted)


async def handle_message(message: dict) -> dict | None:
    """JSON-RPC 요청 하나를 처리한다. 알림(notification)이면 None을 반환."""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def err(code, msg):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": msg}}

    if method == "initialize":
        logger.info("MCP(stdio): initialize")
        return ok(
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                "serverInfo": {"name": SERVER_NAME, "version": _server_version()},
            }
        )

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return ok({})

    if method == "tools/list":
        tools = _mcp_tools()
        logger.info("MCP(stdio): tools/list | count=%d", len(tools))
        return ok({"tools": tools})

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        logger.info("MCP(stdio): tools/call | tool=%s", tool_name)
        return ok(await _call_tool(tool_name, arguments))

    if method == "resources/list":
        return ok(build_resources_list())

    if method == "resources/read":
        uri = params.get("uri", "")
        try:
            resource = await read_resource(
                uri, _law_detail_repo, _precedent_repo, _interpretation_repo, _appeal_repo
            )
        except Exception as e:
            logger.error("resources/read error | uri=%s error=%s", uri, e, exc_info=True)
            return err(-32603, f"리소스 조회 오류: {e}")
        if resource.get("error"):
            return err(-32602, resource["error"])
        return ok(resource)

    if method == "prompts/list":
        return ok({"prompts": _build_prompts_list()})

    if method == "prompts/get":
        prompt = _get_prompt(params.get("name"), params.get("arguments") or {})
        if prompt is None:
            return err(-32602, f"Prompt not found: {params.get('name')}")
        return ok(prompt)

    if request_id is None:
        # 알 수 없는 알림은 조용히 무시
        return None
    return err(-32601, f"Unknown method: {method}")


def _write(response: dict) -> None:
    # default=str: httpx.URL 등 직렬화 불가 타입이 섞여도 응답 전체가
    # 깨지지 않도록 하는 마지막 안전망
    _STDOUT.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
    _STDOUT.flush()


async def main() -> None:
    logger.info("LexGuard MCP (stdio) 시작 | tools=%d", len(TOOLS_LIST))
    stdin = sys.stdin.buffer

    while True:
        # Windows에서 connect_read_pipe는 콘솔/파이프 조합에 따라 실패하므로
        # 블로킹 readline을 스레드로 넘겨 처리한다.
        line = await asyncio.to_thread(stdin.readline)
        if not line:
            break
        # 일부 클라이언트가 첫 줄에 BOM을 붙여 보내면 JSON 파싱이 깨지므로 제거
        text = line.decode("utf-8-sig", errors="replace").strip().lstrip("﻿")
        if not text:
            continue

        try:
            message = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("Parse error: %s", e)
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue

        try:
            response = await handle_message(message)
        except Exception as e:
            logger.error("Internal error: %s", e, exc_info=True)
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {e}"},
            }

        if response is not None:
            _write(response)

    from .utils.http_client import close_async_client, close_sync_client

    await close_async_client()
    close_sync_client()
    logger.info("LexGuard MCP (stdio) 종료")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
