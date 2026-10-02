"""항번호 매칭 테스트.

원문자 표가 ⑩까지만 있고 그 뒤는 목록 위치로 골랐다. 항 필터(HANG)를 건
eflawjosub 응답은 그 항 하나만 오므로, 제11항 이후는 위치가 범위를 벗어나
늘 SUBSECTION_NOT_FOUND였다(실측: 소득세법 시행령 제155조 제23항).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.repositories.law_detail import LawDetailRepository

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕"


def _hangs(numbers):
    return [{"항번호": f"{n} ", "항내용": f"{n} 내용"} for n in numbers]


@pytest.mark.parametrize("hang, expected", [("1", "①"), ("11", "⑪"), ("20", "⑳"), ("23", "㉓"), ("제23항", "㉓"), ("㉓", "㉓")])
def test_원문자_항번호를_끝까지_찾는다(hang, expected):
    item = LawDetailRepository._find_hang_item(_hangs(CIRCLED), hang)
    assert item["항번호"].strip() == expected


def test_항_필터로_하나만_온_응답에서도_찾는다():
    item = LawDetailRepository._find_hang_item(_hangs("㉓"), "23")
    assert item is not None and item["항번호"].strip() == "㉓"


def test_빠진_항이_있으면_위치로_고르지_않는다():
    items = _hangs("①②④")
    assert LawDetailRepository._find_hang_item(items, "3") is None, "③ 대신 ④를 돌려주면 안 된다"
    assert LawDetailRepository._find_hang_item(items, "4")["항번호"].strip() == "④"


def test_항번호가_없으면_위치로_고른다():
    items = [{"항내용": "첫째"}, {"항내용": "둘째"}]
    assert LawDetailRepository._find_hang_item(items, "2")["항내용"] == "둘째"


@pytest.mark.asyncio
async def test_제23항_조회가_성공한다():
    body = {
        "법령": {
            "기본정보": {"시행일자": "20261001"},
            "조문": {
                "조문단위": [{
                    "조문번호": "155",
                    "조문제목": "1세대1주택의 특례",
                    "항": [{"항번호": "㉓ ", "항내용": "㉓ 제167조의3제1항제2호가목 및 다목부터 마목까지의 규정에 해당하는 장기임대주택"}],
                }]
            },
        }
    }

    async def fake_aget(url, params=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "application/json"}
        resp.text = json.dumps(body, ensure_ascii=False)
        resp.json = MagicMock(return_value=body)
        resp.url = "https://www.law.go.kr/DRF/lawService.do"
        resp.raise_for_status = MagicMock()
        return resp

    with patch("src.repositories.law_detail.aget", side_effect=fake_aget):
        res = await LawDetailRepository().get_single_article(
            law_id="290841", article_number="155", hang="23",
            arguments={"env": {"LAW_API_KEY": "testkey123"}},
        )

    assert "error" not in res, res.get("error")
    assert "장기임대주택" in res["content"]
