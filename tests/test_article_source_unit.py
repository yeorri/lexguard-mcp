"""조문 본문을 실제로 꺼낸 조문단위만 원문으로 싣는지.

eflawjosub가 메타만 담긴 조문단위를 주고 본문은 lawjosub 최상위에서
복구한 경우, 남아 있던 메타 단위를 원문으로 실었다. formatter는 원문이
있으면 content를 비우므로 복구한 본문이 사라진 채 success로 나갔다.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.repositories.law_detail import LawDetailRepository
from src.utils.response_formatter import format_mcp_response

BODY = "제53조(연장 근로의 제한) ① 당사자 간에 합의하면 1주 간에 12시간을 한도로 근로시간을 연장할 수 있다."


def _resp(body):
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "application/json"}
    r.text = json.dumps(body, ensure_ascii=False)
    r.json = MagicMock(return_value=body)
    r.url = "https://www.law.go.kr/DRF/lawService.do"
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.asyncio
async def test_lawjosub에서_복구한_본문이_사라지지_않는다():
    async def fake_aget(url, params=None, timeout=None):
        target = (params or {}).get("target")
        if target == "law":
            return _resp({"법령": {"기본정보": {"시행일자": "20250101"}}})
        if target == "eflawjosub":
            # 메타만 있는 조문단위 (조문내용·항 없음)
            return _resp({"법령": {"조문": {"조문단위": [{"조문번호": "53", "조문여부": "조문", "조문시행일자": "20250101"}]}}})
        if target == "lawjosub":
            return _resp({"법령": {"조문내용": BODY}})
        raise AssertionError(f"unexpected target {target}")

    with patch("src.repositories.law_detail.aget", side_effect=fake_aget):
        res = await LawDetailRepository().get_single_article(
            law_id="001872", article_number="53", arguments={"env": {"LAW_API_KEY": "testkey123"}}
        )

    assert "원문" not in res, "본문이 없는 메타 단위를 원문으로 실으면 안 된다"
    payload = json.loads(format_mcp_response(res, "law_article_tool")["content"][0]["text"])
    assert payload["success"] is True
    assert "12시간을 한도로" in payload["content"]

