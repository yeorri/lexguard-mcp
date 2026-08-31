"""법령 버전(시행일자별) 조회 테스트.

이력 API(lsHstInf·lsJoHstInf)는 이 인증키로 항상 0건이고 연혁 본문
(lsHistory)은 HTML만 준다. eflaw의 시행일자별 버전 목록이
"그 문언이 언제 바뀌었나"를 확정할 유일한 경로다.
"""
import pytest

from src.routes.tool_handlers.lookup_tools import handle_law_article, handle_law_history


class _Recorder:
    def __init__(self, ret=None):
        self.calls = []
        self._ret = ret or {"ok": True}

    def __getattr__(self, name):
        async def _fn(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self._ret
        return _fn


@pytest.mark.asyncio
async def test_version_list는_전용_저장소로_간다():
    history = _Recorder()
    smart = _Recorder()
    await handle_law_history(
        {"search_type": "version_list", "query": "조세특례제한법"},
        {"law_history_repo": history, "smart_search": smart},
    )
    assert history.calls[0][0] == "list_law_versions"
    assert not smart.calls, "0건만 돌려주는 이력 API로 가면 안 된다"


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["version_list", "버전목록", "시행일목록"])
async def test_버전목록_별칭(alias):
    history = _Recorder()
    await handle_law_history(
        {"search_type": alias, "query": "소득세법"},
        {"law_history_repo": history, "smart_search": _Recorder()},
    )
    assert history.calls[0][0] == "list_law_versions"


@pytest.mark.asyncio
async def test_기존_이력_조회는_그대로_간다():
    history = _Recorder()
    smart = _Recorder()
    await handle_law_history(
        {"search_type": "law_change", "query": "소득세법"},
        {"law_history_repo": history, "smart_search": smart},
    )
    assert smart.calls[0][0] == "law_history_lookup"
    assert not history.calls


@pytest.mark.asyncio
async def test_law_id로_과거_시점_조문을_조회한다():
    """예전에는 핸들러가 law_id를 버리고 항상 None을 넘겨
    과거 버전 조회가 아예 불가능했다."""
    repo = _Recorder()
    await handle_law_article(
        {"law_id": "286597", "article_number": "97의3"},
        {"law_detail_repo": repo},
    )
    name, args, _ = repo.calls[0]
    assert name == "get_law"
    assert args[0] == "286597", "law_id가 저장소까지 전달돼야 한다"


@pytest.mark.asyncio
async def test_법령명도_law_id도_없으면_안내한다():
    res = await handle_law_article({"article_number": "95"}, {"law_detail_repo": _Recorder()})
    assert "law_name" in res["error"]
