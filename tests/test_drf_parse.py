"""DRF 목록 응답 파서 테스트.

실제 API 응답 구조(2026-08-10 실측)를 고정해 회귀를 막는다.
target마다 wrapper/데이터 키의 철자·대소문자가 달라 과거에 조용히 0건이 됐다.
"""
import pytest

from src.utils.drf_parse import parse_drf_list


def test_판례_표준구조():
    data = {"PrecSearch": {"totalCnt": "3344", "prec": [{"사건명": "A"}, {"사건명": "B"}]}}
    total, items = parse_drf_list(data, "prec")
    assert total == 3344
    assert len(items) == 2


def test_헌재결정례_데이터키가_대문자():
    """DetcSearch 안의 키가 'detc'가 아니라 'Detc'다."""
    data = {"DetcSearch": {"totalCnt": "33", "Detc": [{"사건번호": "2009헌마645"}]}}
    total, items = parse_drf_list(data, "detc")
    assert total == 33
    assert items[0]["사건번호"] == "2009헌마645"


def test_법령해석례_wrapper에_Search가_없음():
    """wrapper가 'ExpcSearch'가 아니라 'Expc'다."""
    data = {"Expc": {"totalCnt": "6", "expc": [{"안건명": "질의회신"}]}}
    total, items = parse_drf_list(data, "expc")
    assert total == 6
    assert items[0]["안건명"] == "질의회신"


def test_부처별해석_cgmExpc():
    """부처별 해석은 wrapper 'CgmExpc' / 키 'cgmExpc'를 쓴다."""
    data = {"CgmExpc": {"totalCnt": "8581", "cgmExpc": [{"안건명": "양도소득세 비과세"}]}}
    total, items = parse_drf_list(data, "expc", "cgmExpc")
    assert total == 8581
    assert len(items) == 1


def test_행정규칙_wrapper_대소문자와_단일객체():
    """wrapper는 'AdmRulSearch'(R 대문자)이고 1건이면 dict로 온다."""
    data = {"AdmRulSearch": {"totalCnt": "1", "admrul": {"행정규칙명": "양도소득세 사무처리규정"}}}
    total, items = parse_drf_list(data, "admrul")
    assert total == 1
    assert isinstance(items, list)
    assert items[0]["행정규칙명"] == "양도소득세 사무처리규정"


def test_행정심판례_wrapper는_Decc():
    data = {"Decc": {"totalCnt": "1501", "decc": [{"사건명": "과징금부과처분 취소청구"}]}}
    total, items = parse_drf_list(data, "decc")
    assert total == 1501
    assert len(items) == 1


def test_자치법규_데이터키가_law():
    data = {"OrdinSearch": {"totalCnt": "885", "law": [{"자치법규명": "가평군 조례"}]}}
    total, items = parse_drf_list(data, "law", "ordin")
    assert total == 885
    assert len(items) == 1


def test_위원회_후보키_없이도_탐색():
    """위원회는 target명이 그대로 키가 되므로 후보 없이도 찾아야 한다."""
    data = {"Ppc": {"totalCnt": "3541", "ppc": [{"안건명": "개인정보 제공"}]}}
    total, items = parse_drf_list(data)
    assert total == 3541
    assert len(items) == 1


def test_메타필드는_데이터로_오인하지_않음():
    """resultMsg 등 메타 필드만 있으면 빈 결과여야 한다."""
    data = {"Ftc": {"resultMsg": "success", "resultCode": "00", "target": "ftc", "totalCnt": "0"}}
    total, items = parse_drf_list(data)
    assert items == []


@pytest.mark.parametrize("bad", [None, {}, [], "문자열", 123])
def test_잘못된_입력은_빈결과(bad):
    assert parse_drf_list(bad, "prec") == (0, [])


def test_totalCnt가_없으면_건수로_대체():
    data = {"Ppc": {"ppc": [{"a": 1}, {"a": 2}]}}
    total, items = parse_drf_list(data, "ppc")
    assert total == 2
    assert len(items) == 2


def test_용어연계는_두단계_중첩():
    """lstrmRlt는 wrapper > 법령용어 > 연계용어 로 한 단계 더 들어간다."""
    data = {
        "lstrmRltService": {
            "검색결과개수": "2",
            "키워드": "소득",
            "법령용어": {"id": "1", "연계용어": [{"일상용어명": "가구소득"}, {"일상용어명": "중간소득"}]},
        }
    }
    total, items = parse_drf_list(data, "연계용어")
    assert total == 2
    assert items[0]["일상용어명"] == "가구소득"


def test_후보키가_있으면_바깥dict를_데이터로_오인하지_않음():
    """1차 탐색이 fallback보다 먼저 돌아야 한다."""
    data = {"S": {"바깥": {"안쪽목록": [{"a": 1}]}}}
    _, items = parse_drf_list(data, "안쪽목록")
    assert items == [{"a": 1}]


def test_검색결과개수도_총건수로_인식():
    data = {"X": {"검색결과개수": "7", "법령용어": {"연계용어": [{"a": 1}]}}}
    total, _ = parse_drf_list(data, "연계용어")
    assert total == 7


# --------------------------------------------------------------------------
# 조문번호 파싱 (가지번호 표기)
# --------------------------------------------------------------------------
from src.repositories.base import BaseLawRepository as _B  # noqa: E402


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("156", "015600"),
        ("제95조", "009500"),
        ("156의3", "015603"),
        ("제156조의3", "015603"),
        # 하이픈·점·언더바 표기도 가지번호로 인식해야 한다.
        # '의'만 보면 156-3이 조용히 제156조로 해석되어 다른 조문이 나온다.
        ("156-3", "015603"),
        ("156.3", "015603"),
        ("156_3", "015603"),
        # 이미 6자리 JO 코드면 그대로 통과
        ("015603", "015603"),
        # 구분자가 없는 붙은 숫자는 쪼개지 않는다
        ("1563", "156300"),
        (None, "000000"),
        ("", "000000"),
    ],
)
def test_조문번호_가지번호_표기(raw, expected):
    assert _B.parse_article_number(raw) == expected
