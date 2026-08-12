"""Legal Term Repository — 법령용어·일상용어·용어 연계·관련법령·지능형 검색.

국가법령정보 지식베이스 계열 API를 담당한다. 실측(2026-08-10)으로 확인한 규약:

    기능                     endpoint        target       비고
    법령용어 목록/본문        lawSearch/Service  lstrm
    지식베이스 법령용어       lawSearch          lstrmAI      wrapper lstrmAISearch
    일상용어                 lawSearch          dlytrm       wrapper dlytrmSearch
    법령용어-일상용어 연계     lawService         lstrmRlt     ★ Service 엔드포인트
    일상용어-법령용어 연계     lawService         dlytrmRlt    ★
    법령용어-조문 연계        lawService         lstrmRltJo   ★
    조문-법령용어 연계        lawService         joRltLstrm   ★
    관련법령                 lawSearch          lsRlt        ★ query가 아니라 ID(법령ID)
    지능형 법령검색           lawSearch          aiSearch
    지능형 연관법령           lawSearch          aiRltLs
    학칙·공단·공공기관        lawSearch/Service  school       wrapper는 AdmRulSearch

연계 4종을 lawSearch.do로 호출하면 본문 없이 빈 응답만 돌아온다.
"""
import json
from typing import Optional

import httpx

from ..utils.drf_parse import parse_drf_list
from ..utils.http_client import aget
from .base import (
    LAW_API_BASE_URL,
    LAW_API_SEARCH_URL,
    DRF_REQUEST_TIMEOUT_SEC,
    BaseLawRepository,
    failure_cache,
    logger,
    search_cache,
)


class LegalTermRepository(BaseLawRepository):
    """법령용어·용어 연계·관련법령·지능형 검색 담당 Repository."""

    async def _call(
        self,
        url: str,
        params: dict,
        cache_key: tuple,
        arguments: Optional[dict],
    ) -> Optional[dict]:
        """DRF 호출 공통 처리. 실패 시 에러 dict, 성공 시 파싱된 JSON 반환."""
        _, api_key_error = self.attach_api_key(params, arguments, url)
        if api_key_error:
            return api_key_error

        response = await aget(url, params=params, timeout=DRF_REQUEST_TIMEOUT_SEC)
        invalid = self.validate_drf_response(response)
        if invalid:
            failure_cache[cache_key] = invalid
            return invalid
        response.raise_for_status()

        text = (response.text or "").strip()
        if not text:
            # 지식베이스 계열은 조건이 안 맞으면 본문 없이 빈 응답을 준다
            return {
                "error": "API가 빈 응답을 반환했습니다.",
                "recovery_guide": "검색어나 파라미터(ID·조문 지정 등)를 확인하세요.",
            }
        try:
            return response.json()
        except json.JSONDecodeError as e:
            return {
                "error": f"API 응답이 유효한 JSON 형식이 아닙니다: {e}",
                "raw_response": text[:300],
            }

    async def _search(
        self,
        target: str,
        list_keys: tuple,
        params: dict,
        cache_key: tuple,
        result_key: str,
        per_page: int,
        arguments: Optional[dict],
        url: str = LAW_API_SEARCH_URL,
    ) -> dict:
        """목록 계열 공통 처리."""
        if cache_key in search_cache:
            return search_cache[cache_key]
        if cache_key in failure_cache:
            return failure_cache[cache_key]

        try:
            data = await self._call(url, params, cache_key, arguments)
            if isinstance(data, dict) and "error" in data:
                failure_cache[cache_key] = data
                return data

            total, items = parse_drf_list(data, *list_keys)
            result = {
                "target": target,
                "total": total,
                result_key: items[:per_page] if per_page else items,
            }
            if not items:
                result["message"] = "검색 결과가 없습니다."
            search_cache[cache_key] = result
            return result

        except httpx.TimeoutException:
            err = {
                "error_code": "API_ERROR_TIMEOUT",
                "error": "API 호출 타임아웃",
                "recovery_guide": "잠시 후 다시 시도하세요.",
            }
            failure_cache[cache_key] = err
            return err
        except httpx.RequestError as e:
            return {"error": f"API 요청 실패: {e}"}
        except Exception as e:
            logger.exception("법령용어 계열 조회 오류 | target=%s", target)
            return {"error": f"예상치 못한 오류: {e}"}

    # ------------------------------------------------------------------ #
    # 용어 조회
    # ------------------------------------------------------------------ #

    async def search_legal_term(
        self,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """법령용어 목록 검색 (target=lstrm)."""
        params = {"target": "lstrm", "type": "JSON", "page": page, "display": per_page}
        if query:
            params["query"] = self.normalize_search_query(query)
        return await self._search(
            "lstrm", ("lstrm", "법령용어"), params,
            ("lstrm", query or "", page, per_page), "terms", per_page, arguments,
        )

    async def search_kb_legal_term(
        self,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """지식베이스 법령용어 조회 (target=lstrmAI)."""
        params = {"target": "lstrmAI", "type": "JSON", "page": page, "display": per_page}
        if query:
            params["query"] = self.normalize_search_query(query)
        return await self._search(
            "lstrmAI", ("법령용어", "lstrm"), params,
            ("lstrmAI", query or "", page, per_page), "terms", per_page, arguments,
        )

    async def search_daily_term(
        self,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """일상용어 조회 (target=dlytrm)."""
        params = {"target": "dlytrm", "type": "JSON", "page": page, "display": per_page}
        if query:
            params["query"] = self.normalize_search_query(query)
        return await self._search(
            "dlytrm", ("일상용어", "dlytrm"), params,
            ("dlytrm", query or "", page, per_page), "terms", per_page, arguments,
        )

    # ------------------------------------------------------------------ #
    # 용어·조문 연계 (lawService.do 사용)
    # ------------------------------------------------------------------ #

    async def link_term_to_daily(
        self, query: str, arguments: Optional[dict] = None
    ) -> dict:
        """법령용어-일상용어 연계 (target=lstrmRlt)."""
        params = {"target": "lstrmRlt", "type": "JSON", "query": query}
        return await self._search(
            "lstrmRlt", ("연계용어",), params,
            ("lstrmRlt", query), "links", 0, arguments, url=LAW_API_BASE_URL,
        )

    async def link_daily_to_term(
        self, query: str, arguments: Optional[dict] = None
    ) -> dict:
        """일상용어-법령용어 연계 (target=dlytrmRlt)."""
        params = {"target": "dlytrmRlt", "type": "JSON", "query": query}
        return await self._search(
            "dlytrmRlt", ("연계용어", "연계법령용어"), params,
            ("dlytrmRlt", query), "links", 0, arguments, url=LAW_API_BASE_URL,
        )

    async def link_term_to_article(
        self, query: str, arguments: Optional[dict] = None
    ) -> dict:
        """법령용어-조문 연계 (target=lstrmRltJo). 용어가 쓰인 조문을 찾는다."""
        params = {"target": "lstrmRltJo", "type": "JSON", "query": query}
        return await self._search(
            "lstrmRltJo", ("연계법령",), params,
            ("lstrmRltJo", query), "articles", 0, arguments, url=LAW_API_BASE_URL,
        )

    async def link_article_to_term(
        self,
        law_name: str,
        article_number: Optional[str] = None,
        arguments: Optional[dict] = None,
    ) -> dict:
        """조문-법령용어 연계 (target=joRltLstrm). 조문에 쓰인 용어를 찾는다."""
        params = {"target": "joRltLstrm", "type": "JSON", "query": law_name}
        if article_number:
            params["JO"] = article_number
        return await self._search(
            "joRltLstrm", ("법령용어", "용어", "items"), params,
            ("joRltLstrm", law_name, article_number or ""), "terms", 0, arguments,
            url=LAW_API_BASE_URL,
        )

    # ------------------------------------------------------------------ #
    # 관련법령 · 지능형 검색
    # ------------------------------------------------------------------ #

    async def search_related_laws(
        self, law_id: str, arguments: Optional[dict] = None
    ) -> dict:
        """관련법령 조회 (target=lsRlt). query가 아니라 법령ID(ID)를 받는다."""
        params = {"target": "lsRlt", "type": "JSON", "ID": law_id}
        return await self._search(
            "lsRlt", ("법령", "law"), params,
            ("lsRlt", law_id), "related_laws", 0, arguments,
        )

    async def ai_search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """지능형 법령검색 (target=aiSearch)."""
        params = {
            "target": "aiSearch",
            "type": "JSON",
            "query": self.normalize_search_query(query),
            "page": page,
            "display": per_page,
        }
        return await self._search(
            "aiSearch", ("법령조문", "law"), params,
            ("aiSearch", query, page, per_page), "articles", per_page, arguments,
        )

    async def ai_related_laws(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """지능형 연관법령 (target=aiRltLs)."""
        params = {
            "target": "aiRltLs",
            "type": "JSON",
            "query": self.normalize_search_query(query),
            "page": page,
            "display": per_page,
        }
        return await self._search(
            "aiRltLs", ("법령조문", "law"), params,
            ("aiRltLs", query, page, per_page), "articles", per_page, arguments,
        )

    # ------------------------------------------------------------------ #
    # 학칙·공단·공공기관
    # ------------------------------------------------------------------ #

    async def search_school_rule(
        self,
        query: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        arguments: Optional[dict] = None,
    ) -> dict:
        """학칙·공단·공공기관 규정 목록 (target=school). wrapper는 AdmRulSearch."""
        params = {"target": "school", "type": "JSON", "page": page, "display": per_page}
        if query:
            params["query"] = self.normalize_search_query(query)
        return await self._search(
            "school", ("admrul", "school"), params,
            ("school", query or "", page, per_page), "rules", per_page, arguments,
        )
