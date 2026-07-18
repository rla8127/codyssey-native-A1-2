"""project_config/prompts.yml 을 로드하고 변수를 치환해 최종 프롬프트 문자열을 만든다.

프롬프트 예시 안에 리터럴 `{like_this}` 표기(JSON 스키마 예시 등)가 포함되어 있어
str.format() 대신 .replace() 로 치환한다(포맷 문자열 충돌 방지).
"""

import json
import threading
from pathlib import Path

import yaml

from project_config.settings import settings

_lock = threading.Lock()
_cache: dict = {}
_cache_mtime: float = -1.0


def _prompts_path() -> Path:
    return settings.config_dir / "prompts.yml"


def _load_prompts() -> dict:
    """prompts.yml 을 읽어 dict 로 반환한다. 파일 mtime 이 바뀌면 다시 읽어 hot-reload."""
    global _cache, _cache_mtime
    path = _prompts_path()
    mtime = path.stat().st_mtime
    with _lock:
        if mtime != _cache_mtime:
            with open(path, encoding="utf-8") as f:
                _cache = yaml.safe_load(f) or {}
            _cache_mtime = mtime
        return _cache


def _fill(template: str, **values) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def build_first_recommendation_messages(date_str: str, strict: bool = False) -> list:
    prompts = _load_prompts()
    system_prompt = prompts["first_recommendation_system_prompt"]
    user_prompt = _fill(prompts["first_recommendation_user_prompt_template"], date=date_str)
    if strict:
        user_prompt += "\n\n" + prompts["first_recommendation_strict_suffix"]
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _restaurants_block(restaurants: list) -> str:
    if not restaurants:
        return "없음"
    return "\n".join(
        f"- {r['name']} | {r['address']} | {r.get('category', '')} | {r.get('url', '')}"
        for r in restaurants
    )


def build_final_report_messages(
    date_str: str, first_json: dict, restaurants_by_city: list, errors_list: list
) -> list:
    """recommended_cities(지역별 상세)와 restaurants_by_city(지역별 맛집)를 지역명 기준으로 엮어
    최종 리포트 프롬프트를 만든다."""
    prompts = _load_prompts()
    cities = first_json.get("recommended_cities") or []
    restaurant_lookup = {item["city"]: item["restaurants"] for item in restaurants_by_city}

    cities_text = ", ".join(c.get("city", "") for c in cities) or "없음"

    cities_detail_text = (
        "\n\n".join(
            f"[{c.get('city')}]\n"
            f"- 날씨: {c.get('weather')}\n"
            f"- 행사/축제: {', '.join(c.get('events') or []) or '없음'}\n"
            f"- 추천 이유: {c.get('reason')}"
            for c in cities
        )
        or "없음"
    )

    restaurants_by_city_text = (
        "\n\n".join(
            f"[{c.get('city')}]\n{_restaurants_block(restaurant_lookup.get(c.get('city'), []))}"
            for c in cities
        )
        or "없음"
    )

    errors_text = "없음" if not errors_list else json.dumps(errors_list, ensure_ascii=False)

    user_prompt = _fill(
        prompts["final_report_user_prompt_template"],
        date=date_str,
        cities_text=cities_text,
        cities_detail_text=cities_detail_text,
        restaurants_by_city_text=restaurants_by_city_text,
        errors_text=errors_text,
    )
    return [
        {"role": "system", "content": prompts["final_report_system_prompt"]},
        {"role": "user", "content": user_prompt},
    ]
