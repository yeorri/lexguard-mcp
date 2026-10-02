"""부칙 조회 테스트.

법령 본문 응답(target=law)에는 부칙단위가 함께 오는데 서버가 조문만 읽고
부칙을 버려, 부칙 조회가 늘 실패했다. 게다가 article_number='부칙 제5조'는
숫자만 남아 본문 제5조가 부칙인 것처럼 반환됐다.

fixture는 민간임대주택에 관한 특별법 현행본(MST 276995) 실제 응답에서
부칙 3건(13499·17482·21065)만 남긴 것이다.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.repositories.base import search_cache
from src.repositories.law_detail import LawDetailRepository
from src.routes.tool_handlers.lookup_tools import handle_law_article
from src.utils.response_formatter import format_mcp_response

FIXTURE = Path(__file__).parent / "fixtures" / "api_responses" / "law_addenda_minteuk.json"
ARGS = {"env": {"LAW_API_KEY": "testkey12345"}}


def _law_body() -> dict:
    with FIXTURE.open(encoding="utf-8") as f:
        return json.load(f)


def _response(body: dict, url: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/json"}
    resp.text = json.dumps(body, ensure_ascii=False)
    resp.json = MagicMock(return_value=body)
    resp.url = url
    resp.raise_for_status = MagicMock()
    return resp


SEARCH_BODY = {
    "LawSearch": {
        "totalCnt": "2",
        "law": [
            {"법령명한글": "민간임대주택에 관한 특별법 시행령", "법령일련번호": "111111"},
            {"법령명한글": "민간임대주택에 관한 특별법", "법령일련번호": "276995"},
        ],
    }
}


class _FakeDrf:
    """lawSearch.do에는 검색 결과, lawService.do에는 법령 본문을 돌려준다."""

    def __init__(self):
        self.calls = []

    async def aget(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if "lawSearch.do" in url:
            return _response(SEARCH_BODY, f"{url}?OC=testkey12345&target=law")
        return _response(_law_body(), f"{url}?OC=testkey12345&target=law&MST={params.get('MST')}")


@pytest.fixture(autouse=True)
def _clear_cache():
    search_cache.clear()
    yield
    search_cache.clear()


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def _fn(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"ok": True}
        return _fn


# --- 핸들러 라우팅 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_addendum을_주면_부칙_경로로_간다():
    repo = _Recorder()
    await handle_law_article(
        {"law_name": "민간임대주택에 관한 특별법", "addendum": "17482"},
        {"law_detail_repo": repo},
    )
    assert [c[0] for c in repo.calls] == ["get_law_addendum"]


@pytest.mark.asyncio
async def test_부칙_제5조를_본문_제5조로_조회하지_않는다():
    repo = _Recorder()
    await handle_law_article(
        {"law_name": "민간임대주택에 관한 특별법", "article_number": "부칙 제5조"},
        {"law_detail_repo": repo},
    )
    name, _, kwargs = repo.calls[0]
    assert name == "get_law_addendum", "본문 조문 조회(get_law)로 가면 제5조 본문이 부칙인 양 반환된다"
    assert kwargs.get("number_required") is True


@pytest.mark.asyncio
async def test_일반_조문은_그대로_본문_조회():
    repo = _Recorder()
    await handle_law_article(
        {"law_name": "민간임대주택에 관한 특별법", "article_number": "5"},
        {"law_detail_repo": repo},
    )
    assert repo.calls[0][0] == "get_law"


# --- 공포번호 파싱 ---------------------------------------------------------


@pytest.mark.parametrize(
    "value, allow_bare, expected",
    [
        ("17482", True, "17482"),
        (17482, True, "17482"),
        ("법률 제17482호", True, "17482"),
        ("법률 제17482호, 2020.8.18.", True, "17482"),
        ("대통령령 제31083호", True, "31083"),
        ("법률 제17482호 부칙 제5조", False, "17482"),
        ("부칙 제5조", False, None),
        ("부칙 제5조 제2호", False, None),
        ("2020.8.18.", True, None),
    ],
)
def test_공포번호_파싱(value, allow_bare, expected):
    assert LawDetailRepository.parse_addendum_number(value, allow_bare=allow_bare) == expected


# --- 저장소 ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("addendum", ["17482", "법률 제17482호"])
async def test_공포번호로_부칙_원문을_반환한다(addendum):
    fake = _FakeDrf()
    with patch("src.repositories.law_detail.aget", side_effect=fake.aget):
        res = await LawDetailRepository().get_law_addendum(
            law_id="276995", addendum=addendum, arguments=ARGS
        )

    assert "error" not in res
    assert res["addendum"] == "17482"
    assert res["원문"]["부칙공포번호"] == "17482"
    body = json.dumps(res["원문"]["부칙내용"], ensure_ascii=False)
    assert "제5조(폐지되는 민간임대주택 종류에 관한 특례)" in body
    assert len(fake.calls) == 1, "law_id를 주면 법령 검색 없이 본문만 받는다"


@pytest.mark.asyncio
async def test_법령명으로_현행_MST를_정확히_찾는다():
    """검색 결과에 시행령이 먼저 와도 이름이 정확히 같은 법률을 골라야 한다."""
    fake = _FakeDrf()
    with patch("src.repositories.law_detail.aget", side_effect=fake.aget):
        res = await LawDetailRepository().get_law_addendum(
            law_name="민간임대주택에 관한 특별법", addendum="17482", arguments=ARGS
        )

    assert res["law_id"] == "276995"
    assert fake.calls[1][1]["MST"] == "276995"
    assert res["원문"]["부칙공포번호"] == "17482"


@pytest.mark.asyncio
async def test_목록을_요청하면_공포번호와_일자만_준다():
    with patch("src.repositories.law_detail.aget", side_effect=_FakeDrf().aget):
        res = await LawDetailRepository().get_law_addendum(
            law_id="276995", addendum="목록", arguments=ARGS
        )

    assert "원문" not in res
    assert res["부칙목록"] == [
        {"부칙공포번호": "13499", "부칙공포일자": "20150828"},
        {"부칙공포번호": "17482", "부칙공포일자": "20200818"},
        {"부칙공포번호": "21065", "부칙공포일자": "20251001"},
    ]


@pytest.mark.asyncio
async def test_없는_공포번호는_목록과_함께_오류():
    with patch("src.repositories.law_detail.aget", side_effect=_FakeDrf().aget):
        res = await LawDetailRepository().get_law_addendum(
            law_id="276995", addendum="31083", arguments=ARGS
        )

    assert res["error_code"] == "ADDENDUM_NOT_FOUND"
    assert "시행령" in res["recovery_guide"], "시행령 부칙을 법률에서 찾은 경우를 안내해야 한다"
    assert len(res["부칙목록"]) == 3


@pytest.mark.asyncio
async def test_조번호만_준_부칙_요청은_공포번호를_요구한다():
    with patch("src.repositories.law_detail.aget", side_effect=_FakeDrf().aget):
        res = await LawDetailRepository().get_law_addendum(
            law_id="276995", addendum="부칙 제5조", arguments=ARGS, number_required=True
        )

    assert res["error_code"] == "ADDENDUM_NUMBER_REQUIRED"
    assert len(res["부칙목록"]) == 3


@pytest.mark.asyncio
async def test_같은_법령의_부칙은_다시_받지_않는다():
    fake = _FakeDrf()
    repo = LawDetailRepository()
    with patch("src.repositories.law_detail.aget", side_effect=fake.aget):
        await repo.get_law_addendum(law_id="276995", addendum="17482", arguments=ARGS)
        await repo.get_law_addendum(law_id="276995", addendum="13499", arguments=ARGS)
    assert len(fake.calls) == 1


# --- MCP 응답 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_MCP_응답에_부칙_원문이_실리고_키는_가려진다():
    with patch("src.repositories.law_detail.aget", side_effect=_FakeDrf().aget):
        res = await LawDetailRepository().get_law_addendum(
            law_id="276995", addendum="17482", arguments=ARGS
        )
    out = format_mcp_response(res, "law_article_tool")
    text = out["content"][0]["text"]
    payload = json.loads(text)

    assert payload["success"] is True
    assert payload["addendum"] == "17482"
    assert payload["원문"]["부칙공포번호"] == "17482"
    assert "부칙단위" in payload["_meta"]["parsing_hint"]
    assert "testkey12345" not in text


@pytest.mark.asyncio
async def test_MCP_오류_응답에도_부칙목록이_실린다():
    with patch("src.repositories.law_detail.aget", side_effect=_FakeDrf().aget):
        res = await LawDetailRepository().get_law_addendum(
            law_id="276995", addendum="31083", arguments=ARGS
        )
    payload = json.loads(format_mcp_response(res, "law_article_tool")["content"][0]["text"])

    assert payload["success"] is False
    assert payload["error_code"] == "ADDENDUM_NOT_FOUND"
    assert len(payload["부칙목록"]) == 3
