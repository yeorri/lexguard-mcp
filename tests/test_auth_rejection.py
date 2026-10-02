"""잘못된 키·미등록 IP 응답을 모든 도구에서 인증 오류로 알리는지.

law.go.kr는 이 경우 401/403이 아니라 HTTP 200 JSON
{"result": "사용자 정보 검증에 실패하였습니다.", "msg": "...IP주소...등록..."}
을 준다(2026-10 실측, lawSearch·lawService 모두). 예전에는 이 본문을 데이터로
읽어 모든 도구가 조용히 0건이나 "법령을 찾을 수 없음"으로 나갔다.
"""
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.repositories.base import BaseLawRepository, search_cache
from src.repositories.law_detail import LawDetailRepository

AUTH_FAIL = {
    "result": "사용자 정보 검증에 실패하였습니다.",
    "msg": "OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요.",
}


def _resp(body, url="https://www.law.go.kr/DRF/lawSearch.do?OC=secretkey123&target=law"):
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "application/json;charset=UTF-8"}
    r.text = json.dumps(body, ensure_ascii=False, indent=4)
    r.json = MagicMock(return_value=body)
    r.url = url
    r.raise_for_status = MagicMock()
    return r


def test_200_JSON_인증_실패를_인증_오류로_본다():
    err = BaseLawRepository.validate_drf_response(_resp(AUTH_FAIL))
    assert err["error_code"] == "API_ERROR_AUTH"
    assert "IP" in err["recovery_guide"]
    assert "secretkey123" not in err["api_url"]


def test_긴_정상_응답은_문구가_있어도_오류로_보지_않는다():
    body = {"법령": {"조문": "개인정보 처리 시 사용자 정보 검증 절차를 둔다. " * 200}}
    assert BaseLawRepository.validate_drf_response(_resp(body)) is None


@pytest.mark.asyncio
async def test_도구도_0건이_아니라_인증_오류로_알린다():
    search_cache.clear()

    async def fake_aget(url, params=None, timeout=None):
        return _resp(AUTH_FAIL)

    with patch("src.repositories.law_detail.aget", side_effect=fake_aget):
        res = await LawDetailRepository().get_law_addendum(
            law_name="민간임대주택에 관한 특별법", addendum="17482",
            arguments={"env": {"LAW_API_KEY": "secretkey123"}},
        )
    assert res["error_code"] == "API_ERROR_AUTH", "LAW_NOT_FOUND로 나가면 원인을 알 수 없다"


def test_httpx_URL도_키를_가린다():
    masked = BaseLawRepository._sanitize_url(
        httpx.URL("https://www.law.go.kr/DRF/lawService.do?OC=secretkey123&target=law")
    )
    assert "secretkey123" not in masked
