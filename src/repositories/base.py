"""
Base Repository - 공통 유틸리티 및 상수
"""

import os
import logging
from cachetools import TTLCache
from typing import Optional, Union
import re
import urllib.parse

# Logger
logger = logging.getLogger("lexguard-mcp")
level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger.setLevel(level)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)
logger.propagate = True

# Cache settings
search_cache = TTLCache(maxsize=200, ttl=1800)  # 검색 결과 30분 캐시


class _StructuralFailureCache:
    """구조적 오류(AUTH·HTML·OTHER)만 5분 캐싱. 타임아웃·네트워크 오류는 저장 안 함.

    error_code 필드가 있는 항목만 저장합니다.  Repository의 except
    httpx.TimeoutException / httpx.RequestError 핸들러가 반환하는 dict는
    error_code 없이 {"error": "..."} 형태이므로 자동으로 캐싱이 스킵됩니다.
    validate_drf_response()가 반환하는 {"error_code": "API_ERROR_AUTH", ...}
    같은 구조적 오류는 정상적으로 캐싱됩니다.
    """

    def __init__(self, maxsize: int, ttl: int) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def __setitem__(self, key, value):
        if isinstance(value, dict) and value.get("error_code"):
            self._cache[key] = value
        # error_code 없으면 (타임아웃·네트워크 오류) 저장하지 않음

    def __getitem__(self, key):
        return self._cache[key]

    def __contains__(self, key):
        return key in self._cache

    def __delitem__(self, key):
        del self._cache[key]


failure_cache = _StructuralFailureCache(maxsize=200, ttl=300)  # 구조적 실패 5분 캐시


def _get_drf_scheme() -> str:
    """Return configured DRF scheme with compatibility fallback."""
    scheme = (
        (os.environ.get("LAW_GO_KR_DRF_SCHEME", "https") or "https").strip().lower()
    )
    if scheme in {"http", "https"}:
        return scheme

    logger.warning(
        "Invalid LAW_GO_KR_DRF_SCHEME=%r; falling back to https",
        scheme,
    )
    return "https"


def _build_drf_url(path: str) -> str:
    return f"{_get_drf_scheme()}://www.law.go.kr/DRF/{path}"


# 국가법령정보센터 API 기본 URL
LAW_API_BASE_URL = _build_drf_url("lawService.do")
LAW_API_SEARCH_URL = _build_drf_url("lawSearch.do")  # 법령 검색용

# DRF HTTP 요청 타임아웃(초) — aget(..., timeout=...) 에서 공통 사용
DRF_REQUEST_TIMEOUT_SEC = 10
DRF_REQUEST_TIMEOUT_LONG_SEC = 30


class BaseLawRepository:
    """법령 Repository의 기본 클래스 - 공통 유틸리티 메서드"""

    # 실무에서 흔히 쓰는 법령 약칭 → 정식 명칭.
    # DRF 법령 검색은 일부 약칭만 인식해서('상증법'은 되고 '조특법'은 안 됨)
    # 약칭으로 부르면 "법령 ID를 찾을 수 없습니다"로 끝난다.
    # 공식 약칭 API(target=lsAbrv)는 검색어를 무시하고 전체 목록만 돌려주므로
    # 조회 경로로 쓸 수 없어 자주 쓰는 것만 직접 매핑한다.
    LAW_NAME_ALIASES: dict = {
        "조특법": "조세특례제한법",
        "조특령": "조세특례제한법 시행령",
        "조특칙": "조세특례제한법 시행규칙",
        "상증법": "상속세 및 증여세법",
        "상증령": "상속세 및 증여세법 시행령",
        "소득법": "소득세법",
        "소득령": "소득세법 시행령",
        "소령": "소득세법 시행령",
        "법인법": "법인세법",
        "법인령": "법인세법 시행령",
        "부가법": "부가가치세법",
        "부가령": "부가가치세법 시행령",
        "국기법": "국세기본법",
        "국징법": "국세징수법",
        "지방세법": "지방세법",
        "종부세법": "종합부동산세법",
        "개인정보법": "개인정보 보호법",
        "근기법": "근로기준법",
        "주임법": "주택임대차보호법",
        "상임법": "상가건물 임대차보호법",
        "민집법": "민사집행법",
    }

    @classmethod
    def resolve_law_name(cls, law_name: Optional[str]) -> Optional[str]:
        """약칭이면 정식 명칭으로 바꾼다. 매핑에 없으면 그대로 반환."""
        if not law_name:
            return law_name
        key = str(law_name).strip()
        return cls.LAW_NAME_ALIASES.get(key, key)

    @staticmethod
    def get_api_key(arguments: Optional[dict] = None) -> str:
        """
        API 키를 가져옵니다.
        Priority: 1) arguments.env, 2) environment variables (.env)
        """
        api_key = ""

        # Priority 1: Get from arguments.env
        if isinstance(arguments, dict) and "env" in arguments:
            env = arguments["env"]
            if isinstance(env, dict) and "LAW_API_KEY" in env:
                api_key = env["LAW_API_KEY"]
                logger.debug("API key from arguments.env")
                return api_key.strip() if isinstance(api_key, str) else api_key

        # Priority 2: Get from .env file / runtime env
        api_key = os.environ.get("LAW_API_KEY", "")
        if not api_key:
            api_key = os.environ.get("LAWGOKR_OC", "")
        if api_key:
            logger.debug("API key from .env file")

        return api_key.strip() if isinstance(api_key, str) else api_key

    @staticmethod
    def is_placeholder_key(api_key: Optional[str]) -> bool:
        """API 키가 비어 있거나 placeholder인지 확인합니다."""
        if not api_key or not isinstance(api_key, str):
            return True
        normalized = api_key.strip().lower()
        if not normalized:
            return True
        placeholders = {
            "your_api_key",
            "your_law_api_key",
            "change_me",
            "placeholder",
            "test",
            "dummy",
            "none",
            "null",
        }
        return normalized in placeholders or normalized.startswith("your_")

    @staticmethod
    def mask_api_key(api_key: Optional[str]) -> str:
        """API 키를 마스킹(앞4+뒤4)하여 반환합니다."""
        if not api_key or not isinstance(api_key, str):
            return ""
        key = api_key.strip()
        if len(key) <= 8:
            return key[:2] + "****" + key[-2:]
        return key[:4] + "****" + key[-4:]

    @classmethod
    def attach_api_key(
        cls,
        params: dict,
        arguments: Optional[dict] = None,
        request_url: Optional[str] = None,
    ):
        """API 키를 params에 추가하고 유효성 검증을 수행합니다."""
        api_key = cls.get_api_key(arguments)
        if cls.is_placeholder_key(api_key):
            return None, {
                "error_code": "API_ERROR_AUTH",
                "missing_reason": "API_ERROR_AUTH",
                "error": "LAW_API_KEY가 설정되지 않았습니다.",
                "recovery_guide": "환경변수 LAW_API_KEY 또는 LAWGOKR_OC에 발급키를 설정하세요.",
                "api_url": request_url,
            }
        params["OC"] = api_key
        logger.info(
            "DRF request | url=%s OC=%s", request_url or "", cls.mask_api_key(api_key)
        )
        return api_key, None

    @staticmethod
    def _sanitize_url(url: str) -> str:
        """URL에서 OC 파라미터를 마스킹하여 반환합니다."""
        if not url:
            return url
        try:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if "OC" in query:
                masked = BaseLawRepository.mask_api_key(query["OC"][0])
                query["OC"] = [masked]
            new_query = urllib.parse.urlencode(query, doseq=True)
            return urllib.parse.urlunparse(parsed._replace(query=new_query))
        except Exception as e:
            logger.debug("URL sanitization failed: %s", e)
            return url

    @staticmethod
    def _has_html_body(body: str) -> bool:
        """응답 본문에 HTML이 포함되어 있는지 확인합니다."""
        if not body:
            return False
        head = body.lstrip()[:1000].lower()
        return head.startswith("<!doctype html") or "<html" in head

    @classmethod
    def validate_drf_response(cls, response) -> Optional[dict]:
        """DRF 응답의 Content-Type/HTML 여부를 검증합니다."""
        content_type = response.headers.get("Content-Type", "")
        body = response.text or ""
        status_code = getattr(response, "status_code", None)
        is_json_or_xml = (
            "application/json" in content_type.lower()
            or "application/xml" in content_type.lower()
            or "text/xml" in content_type.lower()
        )
        is_html = "text/html" in content_type.lower() or cls._has_html_body(body)
        sanitized_url = cls._sanitize_url(getattr(response, "url", ""))
        snippet = " ".join(body.strip().split())
        short_snippet = snippet[:200]

        if status_code in (401, 403):
            logger.warning(
                "DRF response auth error | url=%s status=%s ct=%s",
                sanitized_url,
                status_code,
                content_type,
            )
            return {
                "error_code": "API_ERROR_AUTH",
                "missing_reason": "API_ERROR_AUTH",
                "error": "API 키 인증에 실패했습니다.",
                "recovery_guide": "환경변수 LAW_API_KEY 또는 LAWGOKR_OC에 발급키를 설정하세요.",
                "api_url": sanitized_url,
                "status": status_code,
                "content_type": content_type,
                "short_snippet": short_snippet,
            }

        if is_html:
            logger.warning(
                "DRF response invalid | url=%s status=%s ct=%s snippet=%r",
                sanitized_url,
                status_code,
                content_type,
                short_snippet,
            )
            return {
                "error_code": "API_ERROR_HTML",
                "missing_reason": "API_ERROR_HTML",
                "error": "API가 HTML 안내 페이지를 반환했습니다.",
                "recovery_guide": "API 키 설정 또는 정책/차단 여부를 확인하세요.",
                "api_url": sanitized_url,
                "status": status_code,
                "content_type": content_type,
                "short_snippet": short_snippet,
            }

        if not is_json_or_xml:
            logger.warning(
                "DRF response invalid | url=%s status=%s ct=%s snippet=%r",
                sanitized_url,
                status_code,
                content_type,
                short_snippet,
            )
            return {
                "error_code": "API_ERROR_OTHER",
                "missing_reason": "API_ERROR_OTHER",
                "error": "API 응답 형식이 JSON/XML이 아닙니다.",
                "recovery_guide": "API 서버 상태를 확인하거나 잠시 후 다시 시도하세요.",
                "api_url": sanitized_url,
                "status": status_code,
                "content_type": content_type,
                "short_snippet": short_snippet,
            }
        return None

    @staticmethod
    def normalize_search_query(query: str) -> str:
        """검색어를 정규화합니다."""
        normalized = query.strip()
        normalized = " ".join(normalized.split())
        return normalized

    @staticmethod
    def parse_article_number(article_str: Union[str, int, float, None]) -> str:
        """
        조/항/호 번호를 6자리 숫자로 변환합니다.
        예: '제1조' -> '000100', '제10조의2' -> '001002', '제2항' -> '000200'

        Args:
            article_str: 조/항/호 번호 (문자열 또는 JSON에서 온 int/float)

        Returns:
            6자리 숫자 문자열 (예: '000100')
        """
        if article_str is None:
            return "000000"
        # MCP/JSON에서 조문번호가 int·float로 올 수 있음 (.strip 등 방지)
        if isinstance(article_str, (int, float)):
            article_str = str(int(article_str))
        if not article_str or not str(article_str).strip():
            return "000000"
        article_str = str(article_str).strip()

        # 이미 6자리 JO 코드로 들어온 경우 그대로 사용 (예: '015603')
        if re.fullmatch(r"\d{6}", article_str):
            return article_str

        # 숫자 추출
        numbers = re.findall(r"\d+", article_str)
        if not numbers:
            return "000000"

        main_num = int(numbers[0])

        # 가지번호 구분자: '의' 외에 하이픈·점·언더바도 실무에서 쓰인다.
        # 구분자를 '의'로만 보면 '156-3'이 조용히 제156조로 해석되어
        # 전혀 다른 조문을 반환한다.
        branch = re.search(r"\d+\s*(?:조)?\s*(?:의|[-._])\s*(\d+)", article_str)
        if branch:
            sub_num = int(branch.group(1))
            # 6자리: 앞 4자리는 조 번호, 뒤 2자리는 가지번호
            return f"{main_num:04d}{sub_num:02d}"

        # 6자리: 앞 4자리는 본 번호, 뒤 2자리는 00
        return f"{main_num:04d}00"

    @staticmethod
    def parse_mok(mok_str: str) -> str:
        """
        목 문자를 한글 인코딩하여 반환합니다.
        예: '가' -> '가', '다' -> '다'

        Args:
            mok_str: 목 문자 (예: '가', '나', '다')

        Returns:
            인코딩된 목 문자
        """
        if not mok_str:
            return ""

        # 한글 목 문자만 추출 (가-하)
        mok_char = mok_str.strip()[0] if mok_str.strip() else ""
        if "가" <= mok_char <= "하":
            return mok_char
        return ""
