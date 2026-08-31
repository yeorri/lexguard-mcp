"""format_mcp_response JSON 직렬화 (httpx.URL 등)."""

import json

import httpx

from src.utils.response_formatter import format_mcp_response, sanitize_for_mcp_json


def _payload(mcp_response):
    """MCP 응답 본문을 파싱한다.

    structuredContent는 content[0].text와 같은 데이터를 한 벌 더 실어
    응답을 두 배로 만들기 때문에 제거했다. 본문은 content에서 읽는다.
    """
    import json as _json

    return _json.loads(mcp_response["content"][0]["text"])



def test_sanitize_for_mcp_json_nested_httpx_url():
    u = httpx.URL("https://www.law.go.kr/DRF/lawSearch.do?query=test")
    raw = {"outer": {"api_url": u}, "list": [u]}
    out = sanitize_for_mcp_json(raw)
    assert out["outer"]["api_url"] == str(u)
    assert out["list"][0] == str(u)


def test_format_mcp_response_with_httpx_url_in_api_url():
    u = httpx.URL("https://www.law.go.kr/DRF/lawSearch.do")
    result = format_mcp_response(
        {"query": "근로기준법", "laws": [], "total": 0, "api_url": u},
        "search_law_tool",
    )
    payload = json.loads(result["content"][-1]["text"])
    assert payload["api_url"] == str(u)
    assert _payload(result)["api_url"] == str(u)
