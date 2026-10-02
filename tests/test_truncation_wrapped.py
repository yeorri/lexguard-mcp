"""content[0].text로 감싼 응답의 크기 제한 테스트.

목록을 페이로드 기준으로 한도에 맞춘 뒤 JSON 문자열로 다시 감싸면 따옴표
이스케이프만큼(약 10%) 커져 한도를 넘는다. 그러면 precedents·laws 등은
목록을 통째로 지워 결과가 0건처럼 보였고, 그 밖의 키는 한도를 넘긴 채
나갔다.
"""
import json

import pytest

from src.utils.response_truncator import shrink_response_bytes

LIMIT = 20000


def _wrapped(list_key: str, n: int = 400) -> dict:
    items = [
        {
            "사건번호": f"2025두{i}",
            "사건명": f"양도소득세 \"쟁점\" 부과처분 취소 {i} " + "가" * 200,
            "판례상세링크": f"/DRF/lawService.do?target=prec&ID={i}&type=HTML",
        }
        for i in range(n)
    ]
    payload = {"success": True, "total": n, list_key: items, "api_url": "https://www.law.go.kr/DRF/lawSearch.do"}
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


@pytest.mark.parametrize("list_key", ["precedents", "decisions"])
def test_목록을_지우지_않고_한도_안으로_줄인다(list_key):
    out = shrink_response_bytes(_wrapped(list_key), LIMIT)

    assert len(json.dumps(out, ensure_ascii=False).encode("utf-8")) <= LIMIT
    shown = json.loads(out["content"][0]["text"])
    assert shown.get(list_key), "목록을 통째로 지우면 검색 결과가 0건처럼 보인다"
    assert shown[f"{list_key}_showing"] == len(shown[list_key])
    assert shown[f"{list_key}_total"] == 400
