"""API 키(OC) 마스킹이 api_url 밖의 문자열에도 적용되는지.

DRF 목록 항목의 상세링크('/DRF/lawService.do?OC=…&target=prec&ID=…'),
예외 메시지에 섞인 요청 URL, fetch가 JSON으로 묶은 본문에는 api_url 키가
아닌 곳에 키가 평문으로 들어 있었다. 판례·해석례·헌재·행정규칙·위원회·
자치법규·법령용어·학칙 도구가 모두 키를 노출했다.
"""
import json

from src.utils.response_formatter import format_mcp_response, mask_oc_in_text, sanitize_for_mcp_json

KEY = "secretoc123"


def test_상세링크의_키를_가린다():
    result = {
        "total": 1,
        "precedents": [{
            "사건번호": "2025도6752",
            "판례상세링크": f"/DRF/lawService.do?OC={KEY}&target=prec&ID=614335&type=HTML",
        }],
    }
    text = format_mcp_response(sanitize_for_mcp_json(result), "precedent_lookup_tool")["content"][0]["text"]
    assert KEY not in text
    assert "target=prec&ID=614335" in text, "키 외의 링크는 그대로 둔다"


def test_HTML_이스케이프된_링크와_오류_메시지도_가린다():
    assert KEY not in mask_oc_in_text(f"/DRF/lawService.do?OC={KEY}&amp;target=prec")
    err = sanitize_for_mcp_json({"error": f"예상치 못한 오류: 500 for url 'https://www.law.go.kr/DRF/lawSearch.do?target=law&OC={KEY}'"})
    assert KEY not in err["error"]


def test_fetch처럼_JSON_문자열로_묶인_본문도_가린다():
    inner = json.dumps({"url": f"https://www.law.go.kr/DRF/lawService.do?OC={KEY}&target=detc"}, ensure_ascii=False)
    assert KEY not in json.dumps(sanitize_for_mcp_json({"text": inner}), ensure_ascii=False)


def test_키가_아닌_문자열은_바꾸지_않는다():
    text = "제155조(1세대1주택의 특례) ① 국내에 1주택을 소유한 1세대가 …"
    assert mask_oc_in_text(text) == text

