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


def build_final_report_messages(
    date_str: str, first_json: dict, restaurants: list, errors_list: list
) -> list:
    prompts = _load_prompts()

    restaurants_text = (
        "없음"
        if not restaurants
        else "\n".join(
            f"- {r['name']} | {r['address']} | {r.get('category', '')} | {r.get('url', '')}"
            for r in restaurants
        )
    )
    events_text = ", ".join(first_json.get("events") or []) or "없음"
    errors_text = "없음" if not errors_list else json.dumps(errors_list, ensure_ascii=False)

    user_prompt = _fill(
        prompts["final_report_user_prompt_template"],
        date=date_str,
        recommended_city=first_json.get("recommended_city"),
        weather=first_json.get("weather"),
        events_text=events_text,
        reason=first_json.get("reason"),
        restaurants_text=restaurants_text,
        errors_text=errors_text,
    )
    return [
        {"role": "system", "content": prompts["final_report_system_prompt"]},
        {"role": "user", "content": user_prompt},
    ]
