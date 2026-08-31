"""
응답 크기 제한 유틸리티

한도를 넘으면 목록을 줄이고, 그래도 크면 긴 문자열을 자른다.

한도 설정 근거: 조문 하나가 온전히 들어가야 한다.
소득세법 시행령 제167조의3처럼 호가 많은 조문은 본문만 약 15,000자
(UTF-8 약 40KB)이고, MCP 응답은 content 텍스트와 structuredContent에
같은 내용을 두 번 담으므로 약 80KB가 된다.
한도가 24KB이던 시절에는 이런 조문이 500자로 잘려 각 호가 통째로
사라졌다 — 조문 조회 도구로서는 결과가 없는 것만 못하다.
"""
import json
import logging
from typing import Dict, Any

logger = logging.getLogger("lexguard-mcp")

# 긴 조문 하나가 중복 저장(content + structuredContent)돼도 들어갈 크기
MAX_RESPONSE_SIZE = 120000  # bytes
RESERVE_SIZE = 500  # JSON 구조용 여유 공간 (메타데이터, 필드명 등)
TARGET_SIZE = MAX_RESPONSE_SIZE - RESERVE_SIZE  # 실제 콘텐츠용 크기

# 문자열 절단은 최후의 수단이다. 조문 본문을 500자로 자르면 쓸모가 없어지므로
# 임계값을 크게 잡고, 자를 때도 충분히 남긴다.
FIELD_TRUNCATE_THRESHOLD = 60000  # bytes — 이보다 큰 문자열만 절단 대상
FIELD_TRUNCATE_KEEP = 30000  # chars — 절단 시 남길 분량


def truncate_response(result: Dict[str, Any], max_size: int = TARGET_SIZE) -> Dict[str, Any]:
    """
    응답 크기를 24KB 이하로 제한합니다.

    Args:
        result: MCP 툴 응답 딕셔너리
        max_size: 최대 크기 (기본값: TARGET_SIZE)

    Returns:
        크기가 제한된 응답 딕셔너리
    """
    try:
        # JSON 직렬화하여 크기 확인
        json_str = json.dumps(result, ensure_ascii=False)
        json_size = len(json_str.encode('utf-8'))

        logger.debug(f"Response size: {json_size} bytes (max: {max_size} bytes)")

        # 크기가 제한 이하이면 그대로 반환
        if json_size <= max_size:
            return result

        logger.warning(f"Response size exceeds limit: {json_size} > {max_size} bytes. Truncating...")

        # 크기 초과 시 처리
        truncated_result = result.copy()

        # content 필드가 있으면 처리
        if "content" in truncated_result and isinstance(truncated_result["content"], list):
            for item in truncated_result["content"]:
                if isinstance(item, dict) and "text" in item:
                    text = item["text"]
                    if isinstance(text, str):
                        # 텍스트 크기 확인
                        text_bytes = len(text.encode('utf-8'))
                        # 텍스트가 너무 크면 요약
                        if text_bytes > max_size // 2:
                            item["text"] = summarize_text(text, max_size // 2)
                            item["truncated"] = True
                            # 원본 URL이 있으면 추가
                            if "api_url" in truncated_result:
                                item["full_text_url"] = truncated_result.get("api_url", "")
                            logger.info(f"Text truncated: {text_bytes} -> {len(item['text'].encode('utf-8'))} bytes")

        # 리스트 필드 제한 (너무 긴 리스트는 앞부분만 유지)
        for key, value in list(truncated_result.items()):
            if isinstance(value, list) and len(value) > 10:
                original_length = len(value)
                truncated_result[key] = value[:10]
                truncated_result[f"{key}_truncated"] = True
                truncated_result[f"{key}_total"] = original_length
                truncated_result[f"{key}_showing"] = 10
                logger.info(f"List truncated: {key} ({original_length} -> 10 items)")

        # 다시 크기 확인
        final_json_str = json.dumps(truncated_result, ensure_ascii=False)
        final_size = len(final_json_str.encode('utf-8'))

        # 여전히 크면 더 공격적으로 축소
        if final_size > max_size:
            logger.warning(f"Still too large after truncation: {final_size} bytes. Applying aggressive truncation...")
            truncated_result = aggressive_truncate(truncated_result, max_size)

        final_json_str = json.dumps(truncated_result, ensure_ascii=False)
        final_size = len(final_json_str.encode('utf-8'))
        logger.info(f"Final response size: {final_size} bytes (max: {max_size} bytes)")

        return _sync_content_json(truncated_result)

    except Exception as e:
        logger.exception(f"Error truncating response: {e}")
        # 에러 발생 시 원본 반환 (크기 제한보다 안정성 우선)
        return result


def summarize_text(text: str, max_length: int) -> str:
    """
    텍스트를 요약합니다 (중요 정보 유지).

    Args:
        text: 원본 텍스트
        max_length: 최대 길이 (바이트)

    Returns:
        요약된 텍스트
    """
    if not isinstance(text, str):
        return str(text)

    text_bytes = len(text.encode('utf-8'))
    if text_bytes <= max_length:
        return text

    # 앞부분 + "..." + 뒷부분 구조로 요약
    # UTF-8 바이트 단위로 처리
    front_bytes = max_length // 3
    back_bytes = max_length // 3

    # 앞부분 추출 (바이트 단위)
    front_text = ""
    front_byte_count = 0
    for char in text:
        char_bytes = len(char.encode('utf-8'))
        if front_byte_count + char_bytes > front_bytes:
            break
        front_text += char
        front_byte_count += char_bytes

    # 뒷부분 추출 (바이트 단위)
    back_text = ""
    back_byte_count = 0
    for char in reversed(text):
        char_bytes = len(char.encode('utf-8'))
        if back_byte_count + char_bytes > back_bytes:
            break
        back_text = char + back_text
        back_byte_count += char_bytes

    # 중간 생략 메시지
    ellipsis = "\n\n[... 중간 생략 ...]\n\n"
    ellipsis_bytes = len(ellipsis.encode('utf-8'))

    # 전체 크기 조정
    total_bytes = front_byte_count + ellipsis_bytes + back_byte_count
    if total_bytes > max_length:
        # 뒷부분을 더 줄임
        excess = total_bytes - max_length
        back_text = ""
        back_byte_count = 0
        for char in reversed(text):
            char_bytes = len(char.encode('utf-8'))
            if back_byte_count + char_bytes > (back_bytes - excess):
                break
            back_text = char + back_text
            back_byte_count += char_bytes

    return front_text + ellipsis + back_text


def aggressive_truncate(result: Dict[str, Any], max_size: int) -> Dict[str, Any]:
    """
    공격적인 축소 (최후의 수단).

    Args:
        result: 응답 딕셔너리
        max_size: 최대 크기

    Returns:
        축소된 응답 딕셔너리
    """
    truncated = result.copy()

    # 1) 목록부터 줄인다. 검색 결과 개수를 줄이는 것이
    #    본문을 자르는 것보다 손실이 훨씬 적다.
    for key, value in list(truncated.items()):
        if isinstance(value, list) and len(value) > 5:
            truncated[key] = value[:5]
            truncated[f"{key}_truncated"] = True
            truncated[f"{key}_total"] = len(value)
            truncated[f"{key}_showing"] = 5

    if get_response_size(truncated) <= max_size:
        return truncated

    # 2) 그래도 크면 content 텍스트를 줄인다.
    if "content" in truncated and isinstance(truncated["content"], list):
        for item in truncated["content"]:
            if isinstance(item, dict) and "text" in item:
                text = item.get("text", "")
                if isinstance(text, str) and len(text.encode("utf-8")) > max_size // 2:
                    item["text"] = summarize_text(text, max_size // 2)
                    item["truncated"] = True
                    item["aggressive_truncation"] = True

    if get_response_size(truncated) <= max_size:
        return truncated

    # 3) 마지막으로 아주 긴 문자열 필드를 자른다.
    #    조문 본문이 여기 걸리면 실무에서 쓸 수 없게 되므로 임계값을 높게 둔다.
    for key, value in list(truncated.items()):
        if isinstance(value, str) and key not in ["api_url", "error"]:
            if len(value.encode("utf-8")) > FIELD_TRUNCATE_THRESHOLD:
                truncated[key] = value[:FIELD_TRUNCATE_KEEP] + "... [truncated]"
                logger.info("Field truncated: %s", key)

    return truncated


def get_response_size(result: Dict[str, Any]) -> int:
    """
    응답의 크기를 바이트 단위로 반환합니다.

    Args:
        result: 응답 딕셔너리

    Returns:
        바이트 크기
    """
    try:
        json_str = json.dumps(result, ensure_ascii=False)
        return len(json_str.encode('utf-8'))
    except Exception as e:
        logger.exception(f"Error calculating response size: {e}")
        return 0


def _sync_content_json(result: Dict[str, Any]) -> Dict[str, Any]:
    """structuredContent가 있으면 content의 JSON 텍스트를 동기화합니다."""
    if not isinstance(result, dict):
        return result
    structured = result.get("structuredContent")
    contents = result.get("content")
    if not isinstance(structured, dict) or not isinstance(contents, list) or not contents:
        return result
    try:
        json_text = json.dumps(structured, ensure_ascii=False)
        # 마지막 content를 JSON으로 간주하고 갱신
        contents[-1]["text"] = json_text
    except Exception:
        return result
    return result


def _reduce_structured_content(structured: Dict[str, Any]) -> Dict[str, Any]:
    """구조화된 응답에서 큰 필드를 우선 축소합니다."""
    if not isinstance(structured, dict):
        return structured
    reduced = structured.copy()
    drop_keys = [
        "document_text",
        "document_analysis",
        "retry_plan",
        "response_policy",
        "errors",
        "summary",
        "laws",
        "precedents",
        "interpretations",
        "administrative_appeals"
    ]
    for key in drop_keys:
        if key in reduced:
            reduced.pop(key, None)
    return reduced


def _shrink_content_only(result: Dict[str, Any], max_bytes: int) -> Dict[str, Any]:
    """content[0].text에 담긴 JSON을 줄여 전체 크기를 맞춘다.

    structuredContent를 두지 않는 응답용. 텍스트가 JSON이 아니면
    (설명문 등) 마지막 수단으로 문자열을 자른다.
    """
    blocks = result.get("content")
    if not isinstance(blocks, list) or not blocks:
        return result

    target = None
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            target = block
    if target is None:
        return result

    try:
        payload = json.loads(target["text"])
    except (json.JSONDecodeError, TypeError):
        text = target["text"]
        if len(text.encode("utf-8")) > max_bytes:
            target["text"] = text[:FIELD_TRUNCATE_KEEP] + "... [truncated]"
        return result

    if not isinstance(payload, dict):
        return result

    for _ in range(4):
        payload = aggressive_truncate(payload, max_bytes)
        target["text"] = json.dumps(payload, ensure_ascii=False)
        if get_response_size(result) <= max_bytes:
            return result
        payload = _reduce_structured_content(payload)
        target["text"] = json.dumps(payload, ensure_ascii=False)
        if get_response_size(result) <= max_bytes:
            return result

    return result


def shrink_response_bytes(result: Dict[str, Any], max_bytes: int = MAX_RESPONSE_SIZE) -> Dict[str, Any]:
    """
    최종 JSON 직렬화 기준으로 바이트 크기를 하드 제한합니다.
    """
    try:
        json_str = json.dumps(result, ensure_ascii=False)
        if len(json_str.encode("utf-8")) <= max_bytes:
            return result
    except Exception:
        return result

    truncated = result.copy() if isinstance(result, dict) else result

    # structuredContent 없이 content만 있는 응답(조문 조회·search·fetch)은
    # content[0].text 안의 JSON을 직접 줄인다.
    if isinstance(truncated, dict) and "structuredContent" not in truncated:
        return _shrink_content_only(truncated, max_bytes)

    for _ in range(4):
        if isinstance(truncated, dict) and isinstance(truncated.get("structuredContent"), dict):
            truncated["structuredContent"] = aggressive_truncate(truncated["structuredContent"], max_bytes)
            truncated = _sync_content_json(truncated)

        try:
            if len(json.dumps(truncated, ensure_ascii=False).encode("utf-8")) <= max_bytes:
                return truncated
        except Exception:
            return truncated

        if isinstance(truncated, dict) and isinstance(truncated.get("structuredContent"), dict):
            truncated["structuredContent"] = _reduce_structured_content(truncated["structuredContent"])
            truncated = _sync_content_json(truncated)

    # 마지막 수단: structuredContent 제거 후 재시도
    if isinstance(truncated, dict) and "structuredContent" in truncated:
        trimmed = truncated.copy()
        trimmed.pop("structuredContent", None)
        try:
            if len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8")) <= max_bytes:
                return trimmed
        except Exception:
            return trimmed
        return trimmed

    return truncated

