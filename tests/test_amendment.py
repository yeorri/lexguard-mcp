"""조문 본문에서 개정·삭제 시점을 뽑는 유틸 테스트.

개정이력 API(lsHstInf·lsJoHstInf)가 이 인증키로 항상 0건이라
조문 본문의 <개정 …> 표기가 개정 시점을 확인할 유일한 경로다.
"""
import pytest

from src.utils.amendment import extract_amendment_dates


def test_개정_표기에서_날짜를_뽑는다():
    content = "① 양도소득금액은 … 한다. <개정 2014.12.23, 2019.12.31, 2024.12.31>"
    revisions, deletions = extract_amendment_dates(content)
    assert revisions == ["2024.12.31", "2019.12.31", "2014.12.23"]  # 최신순
    assert deletions == []


def test_삭제_표기를_따로_구분한다():
    content = "④ 삭제 <2022.2.15>\n⑤ 삭제 <2016.2.17>"
    revisions, deletions = extract_amendment_dates(content)
    assert deletions == ["2022.2.15", "2016.2.17"]
    assert revisions == []


def test_신설_전문개정도_개정으로_본다():
    content = "② … <신설 2018.12.24>\n③ … <전문개정 2010.2.18>"
    revisions, _ = extract_amendment_dates(content)
    assert revisions == ["2018.12.24", "2010.2.18"]


def test_중복_날짜는_한_번만():
    content = "① … <개정 2022.2.15>\n② … <개정 2022.2.15, 2023.2.28>"
    revisions, _ = extract_amendment_dates(content)
    assert revisions == ["2023.2.28", "2022.2.15"]


def test_공백이_섞인_날짜도_정규화():
    revisions, _ = extract_amendment_dates("① … <개정 2020. 2. 11>")
    assert revisions == ["2020.2.11"]


@pytest.mark.parametrize("bad", [None, "", "표기가 전혀 없는 조문 내용", 123, [], {}])
def test_표기가_없으면_빈목록(bad):
    assert extract_amendment_dates(bad) == ([], [])


# --------------------------------------------------------------------------
# 조문 조립: 두문(각 호 외의 부분) 보존
# --------------------------------------------------------------------------
from src.repositories.law_detail import LawDetailRepository as _R  # noqa: E402


def test_항이_있어도_두문을_버리지_않는다():
    """상증법 제53조처럼 두문에 한도 규정이 있는 조문이 있다.

    예전에는 항이 있으면 조문내용을 통째로 버려 각 호만 남았고,
    '10년 이내 공제받은 금액과 합한 금액' 같은 한도가 사라졌다.
    """
    article = {
        "조문제목": "증여재산 공제",
        "조문내용": (
            "제53조(증여재산 공제) 거주자가 다음 각 호의 어느 하나에 해당하는 사람으로부터 "
            "증여를 받은 경우에는 그 금액을 공제한다. 이 경우 10년 이내에 공제받은 금액을 "
            "합한 금액이 각 호의 금액을 초과하면 그 초과하는 부분은 공제하지 아니한다."
        ),
        "항": [{"항내용": None, "호": [{"호내용": "1. 배우자로부터 증여를 받은 경우: 6억원"}]}],
    }
    text = _R._render_article_text(article)
    assert "10년 이내에 공제받은 금액" in text
    assert "초과하는 부분은 공제하지 아니한다" in text
    assert "6억원" in text


def test_조문내용이_제목뿐이면_중복하지_않는다():
    """소득세법 제95조는 조문내용이 '제95조(제목)'뿐이라 두문이 없다."""
    article = {
        "조문제목": "양도소득금액과 장기보유 특별공제액",
        "조문내용": "제95조(양도소득금액과 장기보유 특별공제액)",
        "항": [{"항내용": "① 양도소득금액은 양도차익에서 …"}],
    }
    text = _R._render_article_text(article)
    assert text.count("양도소득금액과 장기보유 특별공제액") == 1
    assert "제95조(" not in text


@pytest.mark.parametrize(
    "body,expected",
    [
        ("제95조(제목)", ""),
        ("제53조의2(혼인ㆍ출산 증여재산 공제)", ""),
        ("제53조(증여재산 공제) 거주자가 …", "거주자가 …"),
        ("제167조의3(범위) 다음 각 호의", "다음 각 호의"),
        ("", ""),
    ],
)
def test_두문_추출(body, expected):
    assert _R._extract_chapeau(body) == expected
