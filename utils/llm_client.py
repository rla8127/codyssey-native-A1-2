"""litellm 을 통한 LLM 호출과 Langfuse generation 기록을 담당하는 모듈."""

import json
import logging

import litellm

from project_config.settings import settings
from utils import prompt as prompt_utils

logger = logging.getLogger(__name__)

CITY_DETAIL_KEYS = ["city", "weather", "events", "reason"]

# openai/gemini 두 provider를 같은 alias로 등록해 호출마다 랜덤으로 분산한다(litellm 기본 routing_strategy).
_ROUTER_MODEL_ALIAS = "travel-llm"

router = litellm.Router(
    model_list=[
        {
            "model_name": _ROUTER_MODEL_ALIAS,
            "litellm_params": {"model": settings.openai_model, "api_key": settings.openai_api_key},
        },
        {
            "model_name": _ROUTER_MODEL_ALIAS,
            "litellm_params": {"model": settings.gemini_model, "api_key": settings.gemini_api_key},
        },
    ],
    routing_strategy="simple-shuffle",
)


def classify_exception(exc: Exception) -> str:
    """litellm 은 provider 별 예외를 자체 클래스명으로 정규화해 던지므로,
    isinstance 대신 클래스명 문자열로 분류해 provider 에 상관없이 동작하게 한다."""
    name = exc.__class__.__name__
    if "Authentication" in name or "PermissionDenied" in name:
        return "AUTH_ERROR"
    if "RateLimit" in name:
        return "QUOTA_ERROR"
    if "Timeout" in name or "Connection" in name:
        return "NETWORK_ERROR"
    return "UNKNOWN_ERROR"


def _validate_recommended_cities(data: dict) -> dict:
    cities = data.get("recommended_cities")
    if not isinstance(cities, list) or not cities:
        raise ValueError("recommended_cities가 비어있거나 리스트가 아닙니다")
    for city_info in cities:
        if not isinstance(city_info, dict):
            raise ValueError("recommended_cities 항목이 객체가 아닙니다")
        missing = [k for k in CITY_DETAIL_KEYS if k not in city_info]
        if missing:
            raise ValueError(f"지역 항목에 필수 키 누락: {missing}")
        if not isinstance(city_info.get("events"), list):
            city_info["events"] = [str(city_info["events"])]
    return data


def call_first_recommendation(date_str: str, errors: list, span=None) -> dict:
    for attempt in range(2):
        messages = prompt_utils.build_first_recommendation_messages(date_str, strict=(attempt == 1))
        generation = (
            span.generation(name=f"first_recommendation_attempt_{attempt + 1}", input=messages)
            if span
            else None
        )
        try:
            response = router.completion(
                model=_ROUTER_MODEL_ALIAS,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            content = response.choices[0].message.content
            if generation:
                generation.end(output=content, model=response.model)

            data = _validate_recommended_cities(json.loads(content))
            return data
        except (json.JSONDecodeError, ValueError) as e:
            if generation:
                generation.end(output={"error": str(e)})
            errors.append(
                {"step": "first_recommendation", "type": "PARSE_ERROR", "message": f"시도 {attempt + 1}: {e}"}
            )
        except Exception as e:
            if generation:
                generation.end(output={"error": str(e)})
            errors.append(
                {"step": "first_recommendation", "type": classify_exception(e), "message": str(e)}
            )
            break

    return {
        "recommended_cities": [
            {
                "city": "정보 없음",
                "weather": "정보 없음",
                "events": [],
                "reason": "LLM 응답을 받아오지 못해 기본값으로 대체되었습니다.",
            }
        ]
    }


def _city_fallback_section(city_info: dict, restaurants: list) -> str:
    city = city_info.get("city", "정보 없음")
    weather = city_info.get("weather", "정보 없음")
    events = city_info.get("events") or []
    reason = city_info.get("reason", "정보 없음")

    events_md = "\n".join(f"- {e}" for e in events) if events else "- 데이터 없음"
    if restaurants:
        restaurants_md = "\n".join(
            f"- {r['name']} ({r.get('category', '')}) - {r['address']}"
            + (f" - {r['url']}" if r.get("url") else "")
            for r in restaurants
        )
    else:
        restaurants_md = "- 데이터 없음"

    return f"""### {city}

#### 추천 이유
{reason}

#### 날씨 요약
{weather}

#### 행사/축제
{events_md}

#### 맛집 추천
{restaurants_md}

#### 1일 일정 제안
- 오전: {city} 주요 명소 관광
- 오후: 주변 자연/문화 명소 탐방
- 저녁: 위 맛집 목록 중 한 곳에서 식사
"""


def build_fallback_report(
    date_str: str, first_json: dict, restaurants_by_city: list, errors: list
) -> str:
    """최종 리포트 LLM 호출이 실패해도 결과 파일이 항상 생성되도록 로컬에서 조립하는 대체 리포트."""
    cities = first_json.get("recommended_cities") or []
    restaurant_lookup = {item["city"]: item["restaurants"] for item in restaurants_by_city}

    cities_list_md = "\n".join(f"- {c.get('city', '정보 없음')}" for c in cities) or "- 데이터 없음"
    cities_detail_md = "\n".join(
        _city_fallback_section(c, restaurant_lookup.get(c.get("city"), [])) for c in cities
    )
    errors_md = (
        "\n".join(f"- [{e['step']}] {e['type']}: {e['message']}" for e in errors)
        if errors
        else "- 오류 없음"
    )

    return f"""# {date_str} 국내 여행 추천 리포트

## 추천 지역
{cities_list_md}

## 지역별 상세

{cities_detail_md}
## 오류 요약(errors)
{errors_md}
"""


def call_final_report(
    date_str: str, first_json: dict, restaurants_by_city: list, errors: list, span=None
) -> str:
    messages = prompt_utils.build_final_report_messages(date_str, first_json, restaurants_by_city, errors)
    generation = span.generation(name="final_report", input=messages) if span else None
    try:
        response = router.completion(
            model=_ROUTER_MODEL_ALIAS,
            messages=messages,
            temperature=0.7,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("빈 응답")
        if generation:
            generation.end(output=content, model=response.model)
        return content
    except Exception as e:
        if generation:
            generation.end(output={"error": str(e)})
        error_type = "PARSE_ERROR" if isinstance(e, ValueError) else classify_exception(e)
        errors.append({"step": "report_generation", "type": error_type, "message": str(e)})
        return build_fallback_report(date_str, first_json, restaurants_by_city, errors)
