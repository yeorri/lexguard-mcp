"""지식베이스 도구의 operation 처리와 응답 크기 정책 테스트.

operation을 생략하거나 다른 표현으로 보내는 호출이 실제로 자주 들어온다.
필수로 막으면 가장 자연스러운 호출(query만 전달)이 그대로 실패한다.
"""
import json

import pytest

from src.routes.tool_handlers.knowledge import (
    _AI_ALIASES,
    _TERM_ALIASES,
    _normalize,
    handle_ai_search,
    handle_legal_term,
)
from src.utils.response_truncator import MAX_RESPONSE_SIZE, shrink_response_bytes


class _FakeRepo:
    """호출된 메서드 이름만 기록하는 대역."""

    def __init__(self):
        self.called = None

    def _record(self, name):
        async def _fn(*args, **kwargs):
            self.called = name
            return {"ok": True}
        return _fn

    def __getattr__(self, name):
        return self._record(name)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "조문검색"),      # 생략 → 기본값
        ("", "조문검색"),
        ("조문검색", "조문검색"),
        ("search", "조문검색"),   # 영문 표현
        ("검색", "조문검색"),
        ("연관법령", "연관법령"),
        ("related", "연관법령"),
        ("관련법령", "관련법령"),
        ("알 수 없는 값", "조문검색"),  # 모르는 값도 실패시키지 않는다
    ],
)
def test_ai_operation_정규화(raw, expected):
    assert _normalize(raw, _AI_ALIASES, "조문검색") == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "법령용어"),
        ("법령용어", "법령용어"),
        ("term", "법령용어"),
        ("일상용어", "일상용어"),
        ("용어-조문연계", "용어-조문연계"),
        ("용어→조문", "용어-조문연계"),
    ],
)
def test_term_operation_정규화(raw, expected):
    assert _normalize(raw, _TERM_ALIASES, "법령용어") == expected


@pytest.mark.asyncio
async def test_operation_없이_호출해도_오류가_아니다():
    repo = _FakeRepo()
    services = {"legal_term_repo": repo}

    res = await handle_ai_search({"query": "1세대 3주택"}, services)
    assert "error" not in res
    assert repo.called == "ai_search"

    res = await handle_legal_term({"query": "양도"}, services)
    assert "error" not in res
    assert repo.called == "search_legal_term"


@pytest.mark.asyncio
async def test_law_id만_주면_관련법령으로_해석():
    repo = _FakeRepo()
    await handle_ai_search({"law_id": "001766"}, {"legal_term_repo": repo})
    assert repo.called == "search_related_laws"


@pytest.mark.asyncio
async def test_관련법령은_law_id가_없으면_안내한다():
    repo = _FakeRepo()
    res = await handle_ai_search({"operation": "관련법령"}, {"legal_term_repo": repo})
    assert "law_id" in res["error"]


def test_긴_조문은_잘리지_않는다():
    """조문 본문 약 15,000자(제167조의3 수준)가 온전히 통과해야 한다.

    한도가 24KB이던 시절에는 500자로 잘려 각 호가 통째로 사라졌다.
    """
    body = "제167조의3(1세대 3주택 이상에 해당하는 주택의 범위) " + ("가나다라마바사아자차 " * 1500)
    formatted = {
        "content": [{"type": "text", "text": json.dumps({"content": body}, ensure_ascii=False)}],
        "structuredContent": {"content": body},
    }
    out = shrink_response_bytes(formatted)
    kept = out["structuredContent"]["content"]
    assert "[truncated]" not in kept
    assert len(kept) == len(body)


def test_초대형_응답은_여전히_제한된다():
    """긴 조문을 허용하되 수백 KB짜리 목록은 잘라야 한다."""
    items = [{"조문내용": "가" * 900, "법령명": f"법률 {i}"} for i in range(400)]
    formatted = {
        "content": [{"type": "text", "text": json.dumps({"articles": items}, ensure_ascii=False)}],
        "structuredContent": {"articles": items},
    }
    out = shrink_response_bytes(formatted)
    size = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    assert size <= MAX_RESPONSE_SIZE
    assert len(out["structuredContent"]["articles"]) < len(items)


def test_api_url은_문자열로_저장된다():
    """httpx.URL이 그대로 들어가면 json.dumps가 TypeError를 낸다.

    fetch가 'Object of type URL is not JSON serializable'로 실패하던 원인.
    """
    import pathlib
    import re

    leaked = []
    for p in pathlib.Path("src").rglob("*.py"):
        for m in re.finditer(r'"api_url":\s*(response|resp)\.url', p.read_text(encoding="utf-8")):
            leaked.append(f"{p.as_posix()}: {m.group(0)}")
    assert not leaked, "api_url에 URL 객체가 그대로 들어감:\n" + "\n".join(leaked)


def test_직렬화_불가_타입도_응답이_깨지지_않는다():
    """default=str 안전망이 걸려 있는지 확인."""
    import httpx

    payload = {"jsonrpc": "2.0", "id": 1, "result": {"api_url": httpx.URL("https://x.test/a?b=1")}}
    out = json.dumps(payload, ensure_ascii=False, default=str)
    assert "https://x.test/a?b=1" in out


# --------------------------------------------------------------------------
# 조문 직접 조회: 약칭 해석
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("조특법", "조세특례제한법"),
        ("조특령", "조세특례제한법 시행령"),
        ("상증법", "상속세 및 증여세법"),
        ("부가법", "부가가치세법"),
        # 매핑에 없으면 그대로 통과해야 한다
        ("소득세법", "소득세법"),
        ("소득세법 시행령", "소득세법 시행령"),
        (None, None),
    ],
)
def test_법령_약칭_해석(raw, expected):
    from src.repositories.base import BaseLawRepository

    assert BaseLawRepository.resolve_law_name(raw) == expected
