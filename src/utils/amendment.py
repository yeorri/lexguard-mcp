"""조문 본문에서 개정·삭제 시점을 뽑아낸다.

국가법령정보 DRF의 개정이력 API(lsHstInf, lsJoHstInf)는 이 인증키로
파라미터와 무관하게 항상 totalCnt=0을 반환하고, 연혁 본문(lsHistory)은
JSON을 지원하지 않는다(HTML만 반환). 신청 화면에도 '이력' 항목이 없다.

다행히 조문 본문 자체에 개정 이력이 붙어 있다.

    ① … 한다. <개정 2014.12.23, 2019.12.31, 2024.12.31>
    ⑤ 삭제 <2022.2.15>

이 표기를 뽑으면 "그 문언이 언제 바뀌었나"를 실무 수준에서 확인할 수 있다.
"""
import re
from typing import List, Tuple

# <개정 2014.12.23, 2019.12.31> / <신설 2018.12.24> 형태
_REVISION = re.compile(r"<\s*(?:개정|신설|전문개정|본조신설|제목개정)\s*([^>]+)>")
# 삭제 <2022.2.15> 형태
_DELETION = re.compile(r"삭제\s*<\s*([^>]+)>")
_DATE = re.compile(r"\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}")


def _dates(blob: str) -> List[str]:
    out = []
    for raw in _DATE.findall(blob):
        norm = re.sub(r"\s+", "", raw)
        if norm not in out:
            out.append(norm)
    return out


def extract_amendment_dates(content) -> Tuple[List[str], List[str]]:
    """(개정일자, 삭제일자)를 최신순으로 반환한다.

    본문이 비어 있거나 표기가 없으면 빈 목록을 준다.
    """
    if not content or not isinstance(content, str):
        return [], []

    revisions: List[str] = []
    for blob in _REVISION.findall(content):
        for d in _dates(blob):
            if d not in revisions:
                revisions.append(d)

    deletions: List[str] = []
    for blob in _DELETION.findall(content):
        for d in _dates(blob):
            if d not in deletions:
                deletions.append(d)

    def key(d: str):
        try:
            y, m, day = (int(x) for x in d.split("."))
            return (y, m, day)
        except ValueError:
            return (0, 0, 0)

    return sorted(revisions, key=key, reverse=True), sorted(deletions, key=key, reverse=True)
