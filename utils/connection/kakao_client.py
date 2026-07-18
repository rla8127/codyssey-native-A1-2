"""Kakao Local 키워드 검색 API 클라이언트(맛집 검색 전담)."""

import logging

import requests

from project_config.settings import settings

logger = logging.getLogger(__name__)

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def _fail(errors: list, span, message: str, error_type: str) -> list:
    errors.append({"step": "place_search", "type": error_type, "message": message})
    if span:
        span.end(output={"error": message})
    return []


def search_restaurants(city: str, errors: list, size: int = 5, span=None) -> list:
    query = f"{city} 맛집"
    headers = {"Authorization": f"KakaoAK {settings.kakao_rest_api_key}"}
    params = {"query": query, "size": size, "category_group_code": "FD6"}

    try:
        resp = requests.get(KAKAO_KEYWORD_URL, headers=headers, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.warning("Kakao 장소 검색 네트워크 오류::%s", e)
        return _fail(errors, span, str(e), "NETWORK_ERROR")

    if resp.status_code in (401, 403):
        return _fail(errors, span, f"HTTP {resp.status_code}", "AUTH_ERROR")
    if resp.status_code == 429:
        return _fail(errors, span, f"HTTP {resp.status_code}", "QUOTA_ERROR")
    if resp.status_code != 200:
        return _fail(errors, span, f"HTTP {resp.status_code}: {resp.text[:200]}", "UNKNOWN_ERROR")

    try:
        documents = resp.json().get("documents", [])
    except ValueError as e:
        return _fail(errors, span, str(e), "PARSE_ERROR")

    if not documents:
        return _fail(errors, span, f"0 results for query={query}", "EMPTY_RESULT")

    restaurants = [
        {
            "name": doc.get("place_name", ""),
            "address": doc.get("road_address_name") or doc.get("address_name", ""),
            "category": doc.get("category_name", ""),
            "url": doc.get("place_url", ""),
            "x": float(doc["x"]) if doc.get("x") else None,
            "y": float(doc["y"]) if doc.get("y") else None,
        }
        for doc in documents
    ]
    if span:
        span.end(output=restaurants)
    return restaurants
