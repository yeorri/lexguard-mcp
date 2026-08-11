"""
Administrative Rule Repository - 행정규칙 검색 기능
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


class AdministrativeRuleRepository(BaseLawRepository):
    """행정규칙 검색 관련 기능을 담당하는 Repository"""

    async def search_administrative_rule(
        self,
        query: Optional[str] = None,
        agency: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None
    ) -> dict:
        """행정규칙을 검색합니다."""
        logger.debug("search_administrative_rule called | query=%r agency=%r page=%d per_page=%d",
                    query, agency, page, per_page)

        if per_page < 1:
            per_page = 1
        if per_page > 100:
            per_page = 100

        cache_key = ("administrative_rule", query or "", agency or "", page, per_page)

        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params = {
                "target": "admrul",
                "type": "JSON",
                "page": page,
                "display": per_page
            }

            if query:
                params["query"] = self.normalize_search_query(query)

            if agency:
                # 부처명을 기관코드로 변환 (간단한 매핑)
                agency_code_map = {
                    "고용노동부": "100000",
                    "교육부": "200000",
                    "기획재정부": "300000",
                    # 필요시 더 추가
                }
                if agency in agency_code_map:
                    params["orgCd"] = agency_code_map[agency]

            _, api_key_error = self.attach_api_key(params, arguments, LAW_API_SEARCH_URL)
            if api_key_error:
                return api_key_error

            response = await aget(LAW_API_SEARCH_URL, params=params, timeout=DRF_REQUEST_TIMEOUT_SEC)

            invalid_response = self.validate_drf_response(response)
            if invalid_response:
                return invalid_response
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                return {
                    "error": f"API 응답이 유효한 JSON 형식이 아닙니다: {str(e)}",
                    "query": query,
                    "agency": agency,
                    "api_url": response.url,
                    "recovery_guide": "API 응답 형식 오류입니다. API 서버 상태를 확인하거나 잠시 후 다시 시도하세요."
                }

            result = {
                "query": query,
                "agency": agency,
                "page": page,
                "per_page": per_page,
                "total": 0,
                "rules": [],
                "api_url": response.url
            }

            if isinstance(data, dict):
                # 실제 wrapper는 "AdmRulSearch"(R 대문자)이고, 결과가 1건이면
                # admrul이 배열이 아니라 단일 객체로 온다.
                result["total"], rules = parse_drf_list(data, "admrul")
                result["rules"] = rules[:per_page]

            # total은 있는데 목록이 비어 있는 경우 메타 정보 추가
            if result["total"] and not result["rules"]:
                result["note"] = "API 응답에서 totalCnt는 있으나 행정규칙 목록(admrul)이 비어 있습니다. 국가법령정보센터 응답 구조를 확인하세요."

            search_cache[cache_key] = result
            return result

        except httpx.TimeoutException:
            error_result = {
                "error": "API 호출 타임아웃",
                "recovery_guide": "네트워크 응답 시간이 초과되었습니다. 잠시 후 다시 시도하거나, 인터넷 연결을 확인하세요."
            }
            failure_cache[cache_key] = error_result
            return error_result
        except httpx.RequestError as e:
            error_result = {
                "error": f"API 요청 실패: {str(e)}",
                "recovery_guide": "네트워크 오류입니다. 잠시 후 다시 시도하거나, 인터넷 연결을 확인하세요."
            }
            failure_cache[cache_key] = error_result
            return error_result
        except Exception as e:
            logger.exception("예상치 못한 오류")
            return {
                "error": f"예상치 못한 오류: {str(e)}",
                "recovery_guide": "시스템 오류가 발생했습니다. 서버 로그를 확인하거나 관리자에게 문의하세요."
            }

    async def search_admin_rule_comparison(
        self,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """행정규칙 신구법 비교 목록 검색 (target=admrulOldAndNew, lawSearch.do)."""
        cache_key = ("admrulOldAndNew", query or "", page, per_page)
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params: dict = {
                "target": "admrulOldAndNew",
                "type": "JSON",
                "page": page,
                "display": per_page,
            }
            if query:
                params["query"] = self.normalize_search_query(query)

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
                    if isinstance(v, dict) and "admrulOldAndNew" in v:
                        try:
                            total = int(v.get("totalCnt", 0))
                        except (TypeError, ValueError):
                            total = 0
                        items = v.get("admrulOldAndNew", [])
                        break
                else:
                    try:
                        total = int(data.get("totalCnt", 0))
                    except (TypeError, ValueError):
                        total = 0
                    items = data.get("admrulOldAndNew", [])
                if not isinstance(items, list):
                    items = [items] if items else []

            result = {
                "query": query,
                "page": page,
                "per_page": per_page,
                "total": total,
                "items": items[:per_page],
                "api_url": str(response.url),
            }
            if not items:
                result["message"] = "검색 결과가 없습니다."
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
            logger.exception("search_admin_rule_comparison 오류")
            return {"error": f"예상치 못한 오류: {e}"}

    async def get_admin_rule_comparison(
        self,
        comparison_id: str,
        arguments: Optional[dict] = None,
    ) -> dict:
        """행정규칙 신구법 본문 조회 (target=admrulOldAndNew, lawService.do)."""
        cache_key = ("admrulOldAndNew_detail", comparison_id)
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            params = {"target": "admrulOldAndNew", "type": "JSON", "ID": comparison_id}
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

            result = {"id": comparison_id, "data": data, "api_url": str(response.url)}
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
            logger.exception("get_admin_rule_comparison 오류")
            return {"error": f"예상치 못한 오류: {e}"}

