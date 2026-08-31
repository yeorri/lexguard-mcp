"""공통 스키마 조각 — 여러 도구가 공유하는 page/per_page/error 필드."""

PAGE_PROPS = {
    "page": {"type": "integer", "default": 1, "minimum": 1},
    "per_page": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
}

PAGE_PROPS_10 = {
    "page": {"type": "integer", "default": 1, "minimum": 1},
    "per_page": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
}

ERROR_OUTPUT = {
    "error": {"type": ["string", "null"]},
    "error_code": {"type": ["string", "null"]},
}

# 도구가 무엇을 주는지에 대한 사실 설명만 남긴다.
# 답변 형식·표현 금지 같은 지시는 대화 세션이 판단할 몫이라 서버가 정하지 않는다.
DISCLAIMER = "이 도구는 국가법령정보센터 조회 결과를 그대로 전달합니다."
