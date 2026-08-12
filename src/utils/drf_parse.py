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


def _lookup(container: dict, candidates: Tuple[str, ...]) -> Any:
    """지정된 후보 키를 대소문자 무시하고 찾는다. 못 찾으면 None."""
    if not isinstance(container, dict):
        return None
    lowered = {k.lower(): k for k in container}
    for cand in candidates:
        actual = lowered.get(cand.lower())
        if actual is not None:
            return container[actual]
    return None


def _fallback(container: dict) -> Any:
    """메타가 아닌 첫 list/dict 값을 데이터로 본다.

    위원회처럼 target마다 데이터 키 이름이 다른 경우를 커버한다.
    """
    if not isinstance(container, dict):
        return None
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

    # 탐색 대상: wrapper(1단) → 평면 → 2단 중첩.
    # 용어 연계 API처럼 실제 목록이 wrapper > 법령용어 > 연계용어 로
    # 한 단계 더 들어가 있는 경우가 있다.
    level1 = [v for v in data.values() if isinstance(v, dict)]
    level2 = [v for c in level1 for v in c.values() if isinstance(v, dict)]
    containers = level1 + [data] + level2

    # 총건수는 데이터가 있는 단계가 아니라 상위 wrapper에 있을 수 있으므로
    # (예: lstrmRltService.검색결과개수) 모든 단계를 후보로 둔다.
    count_sources = [data] + level1 + level2

    # 1차: 지정된 후보 키를 모든 단계에서 먼저 찾는다.
    #      (fallback을 먼저 돌리면 바깥 dict를 데이터로 오인한다)
    if candidate_keys:
        for container in containers:
            items = _lookup(container, candidate_keys)
            if items is not None:
                return _finish(items, container, count_sources)

    # 2차: 후보가 없거나 못 찾으면 메타가 아닌 첫 list/dict를 데이터로 본다.
    for container in containers:
        items = _fallback(container)
        if items is not None:
            return _finish(items, container, count_sources)

    return 0, []


def _finish(items: Any, container: dict, count_sources: List[dict]) -> Tuple[int, List[dict]]:
    if not isinstance(items, list):
        items = [items] if items else []

    for key in ("totalCnt", "검색결과개수"):
        for src in [container, *count_sources]:
            total = _to_int(src.get(key))
            if total:
                return total, items

    return len(items), items
