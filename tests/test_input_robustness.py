"""클라이언트 입력 형태에 대한 방어.

- stdio에 배치([...])나 원시값이 오면 처리 태스크가 .get()에서 죽어 응답이 없었다.
- law_id를 숫자로 보내면 저장소의 .strip()에서 죽었다.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.routes.tool_handlers.lookup_tools import handle_law_article


def test_stdio는_객체가_아닌_메시지에도_응답한다():
    """배치([...])나 원시값을 보내면 처리 태스크가 죽어 응답이 없었다."""
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(root / "run_stdio.py")],
        input='[1]\n"x"\n', capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=root,
    )
    replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert [r["error"]["code"] for r in replies] == [-32600, -32600]


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def _fn(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"ok": True}
        return _fn


@pytest.mark.asyncio
async def test_숫자로_온_law_id도_받는다():
    repo = _Recorder()
    await handle_law_article({"law_id": 286597, "article_number": "97의3"}, {"law_detail_repo": repo})
    assert repo.calls[0][1][0] == "286597"
