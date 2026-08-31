"""
Law History Repository - 법령 변경이력·조문 개정이력 검색
"""
import httpx
from ..utils.http_client import aget
from ..utils.drf_parse import parse_drf_list
import json
from typing import Optional
from .base import (
    BaseLawRepository,
    logger,
    LAW_API_SEARCH_URL,
    LAW_API_BASE_URL,
    search_cache,
    failure_cache,
    DRF_REQUEST_TIMEOUT_SEC,
)


class LawHistoryRepository(BaseLawRepository):
    """법령 변경이력(lsHstInf) 및 조문 개정이력(lsJoHstInf) 담당 Repository"""

    async def list_law_versions(
        self,
        law_name: str,
        page: int = 1,
        per_page: int = 50,
        arguments: Optional[dict] = None,
    ) -> dict:
        """법령의 시행일자별 버전 목록을 조회한다 (target=eflaw).

        이력 API(lsHstInf·lsJoHstInf)는 이 인증키로 항상 0건이고 연혁 본문
        (lsHistory)은 HTML만 준다. 그래서 "그 문언이 언제 바뀌었나"를
        확인할 길이 없었는데, eflaw는 시행일자별 버전을 법령일련번호(MST)와
        함께 준다. 그 MST로 과거 시점 조문을 조회하면 개정 전후를 대조할 수 있다.
        """
        if not law_name or not str(law_name).strip():
            return {
                "error": "law_name이 필요합니다.",
                "recovery_guide": "버전 목록을 조회할 법령명을 지정하세요.",
            }

        law_name = self.resolve_law_name(str(law_name).strip())
        cache_key = ("eflaw_versions", law_name, page, per_page)
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params = {
                "target": "eflaw",
                "type": "JSON",
                "query": self.normalize_search_query(law_name),
                "page": page,
                "display": per_page,
            }
            _, api_key_error = self.attach_api_key(params, arguments, LAW_API_SEARCH_URL)
            if api_key_error:
                return api_key_error

            response = await aget(LAW_API_SEARCH_URL, params=params, timeout=DRF_REQUEST_TIMEOUT_SEC)
            invalid = self.validate_drf_response(response)
            if invalid:
                failure_cache[cache_key] = invalid
                return invalid
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                return {"error": f"API 응답이 유효한 JSON 형식이 아닙니다: {e}",
                        "api_url": str(response.url)}

            total, items = parse_drf_list(data, "law")

            # 이름이 다른 법령(시행령·시행규칙 등)이 함께 잡히므로 정확히 일치하는 것만 남긴다
            versions = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if (item.get("법령명한글") or "").strip() != law_name:
                    continue
                versions.append({
                    "시행일자": item.get("시행일자"),
                    "법령일련번호": item.get("법령일련번호"),
                    "현행연혁코드": item.get("현행연혁코드"),
                    "공포일자": item.get("공포일자"),
                    "공포번호": item.get("공포번호"),
                    "제개정구분명": item.get("제개정구분명"),
                })

            versions.sort(key=lambda v: str(v.get("시행일자") or ""), reverse=True)

            result = {
                "law_name": law_name,
                "total": total,
                "versions": versions,
                "api_url": str(response.url),
                "note": (
                    "법령일련번호(MST)를 law_article_tool의 mst 인자로 넘기면 "
                    "그 시점 조문을 조회할 수 있습니다. 두 시점을 각각 조회해 "
                    "대조하면 개정·삭제 시점을 확정할 수 있습니다."
                ),
            }
            if not versions:
                result["message"] = "해당 법령명과 정확히 일치하는 버전을 찾지 못했습니다."

            search_cache[cache_key] = result
            return result

        except httpx.TimeoutException:
            err = {"error_code": "API_ERROR_TIMEOUT", "error": "API 호출 타임아웃",
                   "recovery_guide": "잠시 후 다시 시도하세요."}
            failure_cache[cache_key] = err
            return err
        except httpx.RequestError as e:
            return {"error": f"API 요청 실패: {e}"}
        except Exception as e:
            logger.exception("법령 버전 목록 조회 오류 | law_name=%s", law_name)
            return {"error": f"예상치 못한 오류: {e}"}

    # ------------------------------------------------------------------ #
    # 법령 변경이력 (target=lsHstInf) — lawSearch.do
    # ------------------------------------------------------------------ #

    async def search_law_change_history(
        self,
        query: Optional[str] = None,
        law_id: Optional[str] = None,
        reg_dt: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """법령 변경이력 목록 검색 (target=lsHstInf).

        Args:
            query: 법령명 검색어
            law_id: 법령 ID (lsId)
            reg_dt: 기준 일자 (YYYYMMDD, 해당 일자 기준 변경이력)
            page: 페이지 번호
            per_page: 페이지당 결과 수
            arguments: API 키 등 추가 인자
        """
        cache_key = ("lsHstInf", query or "", law_id or "", reg_dt or "", page, per_page)
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params: dict = {
                "target": "lsHstInf",
                "type": "JSON",
                "page": page,
                "display": per_page,
            }
            if query:
                params["query"] = self.normalize_search_query(query)
            if law_id:
                params["lsId"] = law_id
            if reg_dt:
                params["regDt"] = reg_dt

            _, err = self.attach_api_key(params, arguments, LAW_API_SEARCH_URL)
            if err:
                return err

            response = await aget(LAW_API_SEARCH_URL, params=params, timeout=DRF_REQUEST_TIMEOUT_SEC)
            invalid = self.validate_drf_response(response)
            if invalid:
                failure_cache[cache_key] = invalid
                return invalid
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                return {"error": f"JSON 파싱 오류: {e}"}

            total, items = 0, []
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, dict) and "lsHstInf" in v:
                        try:
                            total = int(v.get("totalCnt", 0))
                        except (TypeError, ValueError):
                            total = 0
                        items = v.get("lsHstInf", [])
                        break
                else:
                    try:
                        total = int(data.get("totalCnt", 0))
                    except (TypeError, ValueError):
                        total = 0
                    items = data.get("lsHstInf", [])
                if not isinstance(items, list):
                    items = [items] if items else []

            result = {
                "query": query,
                "law_id": law_id,
                "reg_dt": reg_dt,
                "page": page,
                "per_page": per_page,
                "total": total,
                "items": items[:per_page],
                "api_url": str(response.url),
            }
            if not items:
                # 이 인증키로는 이력 계열 API(lsHstInf·lsJoHstInf)가 파라미터와
                # 무관하게 항상 0건을 반환한다(인증 오류가 아니라 정상 응답).
                # 조회가 막힌 것인지 자료가 없는 것인지 호출자가 구분할 수 있게 안내한다.
                result["message"] = "검색 결과가 없습니다."
                result["note"] = (
                    "개정이력 API는 현재 인증키로 데이터가 제공되지 않습니다"
                    "(파라미터와 무관하게 0건). 개정·삭제 시점은 law_article_tool로"
                    " 조문을 조회하면 응답의 개정일자·삭제일자 필드에서 확인할 수 있습니다."
                )
            search_cache[cache_key] = result
            return result

        except httpx.TimeoutException:
            err = {
                "error_code": "API_ERROR_TIMEOUT",
                "missing_reason": "API_ERROR_TIMEOUT",
                "error": "API 호출 타임아웃",
                "recovery_guide": "잠시 후 다시 시도하세요.",
            }
            failure_cache[cache_key] = err
            return err
        except httpx.RequestError as e:
            return {"error": f"API 요청 실패: {e}"}
        except Exception as e:
            logger.exception("search_law_change_history 오류")
            return {"error": f"예상치 못한 오류: {e}"}

    # ------------------------------------------------------------------ #
    # 일자별 조문 개정이력 (target=lsJoHstInf) — lawSearch.do
    # ------------------------------------------------------------------ #

    async def search_article_change_history(
        self,
        query: Optional[str] = None,
        law_id: Optional[str] = None,
        reg_dt: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """일자별 조문 개정이력 목록 검색 (target=lsJoHstInf, lawSearch.do)."""
        cache_key = ("lsJoHstInf_search", query or "", law_id or "", reg_dt or "", page, per_page)
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params: dict = {
                "target": "lsJoHstInf",
                "type": "JSON",
                "page": page,
                "display": per_page,
            }
            if query:
                params["query"] = self.normalize_search_query(query)
            if law_id:
                params["lsId"] = law_id
            if reg_dt:
                params["regDt"] = reg_dt

            _, err = self.attach_api_key(params, arguments, LAW_API_SEARCH_URL)
            if err:
                return err

            response = await aget(LAW_API_SEARCH_URL, params=params, timeout=DRF_REQUEST_TIMEOUT_SEC)
            invalid = self.validate_drf_response(response)
            if invalid:
                failure_cache[cache_key] = invalid
                return invalid
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                return {"error": f"JSON 파싱 오류: {e}"}

            total, items = 0, []
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, dict) and "lsJoHstInf" in v:
                        try:
                            total = int(v.get("totalCnt", 0))
                        except (TypeError, ValueError):
                            total = 0
                        items = v.get("lsJoHstInf", [])
                        break
                else:
                    try:
                        total = int(data.get("totalCnt", 0))
                    except (TypeError, ValueError):
                        total = 0
                    items = data.get("lsJoHstInf", [])
                if not isinstance(items, list):
                    items = [items] if items else []

            result = {
                "query": query,
                "law_id": law_id,
                "reg_dt": reg_dt,
                "page": page,
                "per_page": per_page,
                "total": total,
                "items": items[:per_page],
                "api_url": str(response.url),
            }
            if not items:
                # 이 인증키로는 이력 계열 API(lsHstInf·lsJoHstInf)가 파라미터와
                # 무관하게 항상 0건을 반환한다(인증 오류가 아니라 정상 응답).
                # 조회가 막힌 것인지 자료가 없는 것인지 호출자가 구분할 수 있게 안내한다.
                result["message"] = "검색 결과가 없습니다."
                result["note"] = (
                    "개정이력 API는 현재 인증키로 데이터가 제공되지 않습니다"
                    "(파라미터와 무관하게 0건). 개정·삭제 시점은 law_article_tool로"
                    " 조문을 조회하면 응답의 개정일자·삭제일자 필드에서 확인할 수 있습니다."
                )
            search_cache[cache_key] = result
            return result

        except httpx.TimeoutException:
            err = {
                "error_code": "API_ERROR_TIMEOUT",
                "missing_reason": "API_ERROR_TIMEOUT",
                "error": "API 호출 타임아웃",
                "recovery_guide": "잠시 후 다시 시도하세요.",
            }
            failure_cache[cache_key] = err
            return err
        except httpx.RequestError as e:
            return {"error": f"API 요청 실패: {e}"}
        except Exception as e:
            logger.exception("search_article_change_history 오류")
            return {"error": f"예상치 못한 오류: {e}"}

    # ------------------------------------------------------------------ #
    # 조문별 변경이력 (target=lsJoHstInf) — lawService.do
    # ------------------------------------------------------------------ #

    async def get_article_change_history(
        self,
        law_id: str,
        jo_no: Optional[str] = None,
        arguments: Optional[dict] = None,
    ) -> dict:
        """조문별 변경이력 조회 (target=lsJoHstInf, lawService.do).

        Args:
            law_id: 법령 ID (lsId)
            jo_no: 조문 번호 (joNo, 예: '000100')
            arguments: API 키 등 추가 인자
        """
        cache_key = ("lsJoHstInf_detail", law_id, jo_no or "")
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params: dict = {
                "target": "lsJoHstInf",
                "type": "JSON",
                "lsId": law_id,
            }
            if jo_no:
                params["joNo"] = jo_no

            _, err = self.attach_api_key(params, arguments, LAW_API_BASE_URL)
            if err:
                return err

            response = await aget(LAW_API_BASE_URL, params=params, timeout=DRF_REQUEST_TIMEOUT_SEC)
            invalid = self.validate_drf_response(response)
            if invalid:
                failure_cache[cache_key] = invalid
                return invalid
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                return {"error": f"JSON 파싱 오류: {e}"}

            result = {
                "law_id": law_id,
                "jo_no": jo_no,
                "data": data,
                "api_url": str(response.url),
            }
            search_cache[cache_key] = result
            return result

        except httpx.TimeoutException:
            err = {
                "error_code": "API_ERROR_TIMEOUT",
                "missing_reason": "API_ERROR_TIMEOUT",
                "error": "API 호출 타임아웃",
                "recovery_guide": "잠시 후 다시 시도하세요.",
            }
            failure_cache[cache_key] = err
            return err
        except httpx.RequestError as e:
            return {"error": f"API 요청 실패: {e}"}
        except Exception as e:
            logger.exception("get_article_change_history 오류")
            return {"error": f"예상치 못한 오류: {e}"}
