"""국가법령정보 DRF 목록 응답 파싱 공통 유틸.

DRF는 target마다 wrapper 키와 데이터 키의 철자·대소문자가 제각각이다.
실측(2026-08-10, OC=yeorri) 결과:

    target          wrapper         데이터 키   형태
    prec            PrecSearch      prec        list
    detc            DetcSearch      Detc        list      ← 데이터 키만 대문자
    expc            Expc            expc        list      ← wrapper에 Search 없음
    decc            Decc            decc        list
    admrul          AdmRulSearch    admrul      dict      ← R이 대문자, 1건이면 dict
    ordin           OrdinSearch     law         list      ← 데이터 키가 law
    *CgmExpc        CgmExpc         cgmExpc     list      ← 부처별 해석 공통
    ppc/nlrc/...    Ppc/Nlrc/...    ppc/nlrc    list/dict ← 위원회별로 다름

키를 하드코딩하면 target 하나만 달라져도 조용히 "검색 결과 0건"이 되어
권한 문제처럼 보인다. 그래서 대소문자를 무시하고 후보 키를 찾고,
후보가 없으면 메타 필드가 아닌 첫 번째 list/dict 값을 데이터로 간주한다.
"""
from typing import Any, List, Tuple

# 목록 응답에서 데이터가 아닌 메타 필드 (소문자 비교용)
_META_KEYS = {
    "resultmsg",
    "resultcode",
    "target",
    "page",
    "section",
    "numofrows",
    "totalcnt",
    "키워드",
}


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _find_items(container: dict, candidates: Tuple[str, ...]) -> Any:
    """container에서 데이터 배열을 찾는다. 못 찾으면 None."""
    if not isinstance(container, dict):
        return None

    lowered = {k.lower(): k for k in container}

    # 1) 지정된 후보 키를 대소문자 무시하고 탐색
    for cand in candidates:
        actual = lowered.get(cand.lower())
        if actual is not None:
            return container[actual]

    # 2) 후보가 없으면 메타가 아닌 첫 list/dict 값을 데이터로 본다
    #    (위원회처럼 target마다 키가 다른 경우를 커버)
    for key, value in container.items():
        if key.lower() in _META_KEYS:
            continue
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and value and not _is_wrapper(value):
            return value

    return None


def _is_wrapper(candidate: dict) -> bool:
    """totalCnt를 가진 dict는 레코드가 아니라 wrapper로 본다.

    결과가 0건이면 wrapper 안에 메타 필드만 남는데, 이때 wrapper 자체를
    레코드로 오인해 "1건"으로 보고하는 것을 막는다.
    """
    return any(k.lower() == "totalcnt" for k in candidate)


def parse_drf_list(data: Any, *candidate_keys: str) -> Tuple[int, List[dict]]:
    """DRF 목록 응답에서 (총건수, 항목 리스트)를 추출한다.

    Args:
        data: 응답 JSON (dict)
        *candidate_keys: 데이터 배열 키 후보. 대소문자는 무시된다.
                         비워두면 메타가 아닌 첫 list/dict를 사용한다.

    Returns:
        (total, items). 파싱 실패 시 (0, []).
    """
    if not isinstance(data, dict) or not data:
        return 0, []

    # wrapper가 있는 구조와 평면 구조를 모두 시도한다.
    # wrapper 안에 totalCnt가 있는 것이 일반적이므로 wrapper를 먼저 본다.
    containers = [v for v in data.values() if isinstance(v, dict)]
    containers.append(data)

    for container in containers:
        items = _find_items(container, candidate_keys)
        if items is None:
            continue
        if not isinstance(items, list):
            items = [items] if items else []
        total = _to_int(container.get("totalCnt"))
        if total == 0:
            total = _to_int(data.get("totalCnt")) or len(items)
        return total, items

    return 0, []
