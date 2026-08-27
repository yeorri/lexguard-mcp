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
