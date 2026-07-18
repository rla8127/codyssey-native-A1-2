"""국내 여행 추천 CLI 엔트리포인트: 인자 파싱과 전체 흐름 오케스트레이션을 담당한다."""

import argparse
import json
import logging
import sys
from datetime import date, datetime

from project_config.settings import settings
from utils.connection.kakao_client import search_restaurants
from utils.connection.langfuse_manager import langfuse_manager
from utils.connection.redis_cache import redis_cache_manager
from utils.llm_client import call_final_report, call_first_recommendation

logging.basicConfig(level=logging.INFO, format="%(asctime)s :: %(levelname)s :: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ["openai_api_key", "kakao_rest_api_key"]


def valid_date(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"날짜 형식이 올바르지 않습니다: '{value}' (예: 2026-03-15)"
        )
    if parsed < date.today():
        raise argparse.ArgumentTypeError(
            f"과거 날짜는 입력할 수 없습니다: '{value}' (오늘 날짜: {date.today().isoformat()})"
        )
    return value


def parse_args():
    parser = argparse.ArgumentParser(
        description="LLM API와 지도 API를 조합한 국내 여행 추천 프로그램"
    )
    parser.add_argument(
        "-date",
        "--date",
        dest="date",
        required=True,
        type=valid_date,
        metavar="YYYY-MM-DD",
        help="여행 날짜 (형식: YYYY-MM-DD)",
    )
    return parser.parse_args()


def check_required_settings():
    missing = [name.upper() for name in REQUIRED_SETTINGS if not getattr(settings, name)]
    if missing:
        print(f"[오류] 다음 API 키가 설정되지 않았습니다: {', '.join(missing)}")
        print()
        print("설정 방법:")
        print("  1) 프로젝트 루트에 .env 파일을 만들고 아래처럼 입력하세요 (.env.example 참고)")
        print("       OPENAI_API_KEY=your_key_here")
        print("       KAKAO_REST_API_KEY=your_key_here")
        print("  2) 또는 터미널에서 환경변수로 직접 설정하세요")
        print("       export OPENAI_API_KEY=\"YOUR_KEY\"")
        print("       export KAKAO_REST_API_KEY=\"YOUR_KEY\"")
        sys.exit(1)


def save_results(date_str, first_json, restaurants_by_city, errors, report_md):
    results_dir = settings.results_dir
    results_dir.mkdir(exist_ok=True, parents=True)

    data = {
        "date": date_str,
        "recommended": first_json,
        "restaurants_by_city": restaurants_by_city,
        "errors": errors,
    }
    json_path = results_dir / f"{date_str}_travel_data.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = results_dir / f"{date_str}_travel_plan.md"
    md_path.write_text(report_md, encoding="utf-8")

    return json_path, md_path


def main():
    args = parse_args()
    check_required_settings()

    date_str = args.date
    errors = []

    langfuse_client = langfuse_manager.get_client()
    trace = langfuse_client.trace(name="travel_planner", input={"date": date_str})

    cached = redis_cache_manager.get(date_str)
    if cached:
        print(f"[캐시] Redis에 저장된 {date_str} 데이터를 재사용합니다 (1차 추천/맛집 검색 API 호출 생략)")
        first_json = cached["recommended"]
        restaurants_by_city = cached["restaurants_by_city"]
        trace.update(metadata={"cache_hit": True})
    else:
        print("[1/3] 1차 추천 생성 중(LLM)...")
        span = trace.span(name="first_recommendation", input={"date": date_str})
        first_json = call_first_recommendation(date_str, errors, span=span)
        span.end(output=first_json)
        cities_preview = ", ".join(c.get("city", "") for c in first_json.get("recommended_cities", []))
        print(f'    - recommended_cities: "{cities_preview}"')

        print("[2/3] 맛집 검색 중(지도/장소 API)...")
        restaurants_by_city = []
        for city_info in first_json.get("recommended_cities", []):
            city = city_info.get("city", "")
            span = trace.span(name=f"place_search:{city}", input={"city": city})
            errors_before = len(errors)
            restaurants = search_restaurants(city, errors, span=span)
            restaurants_by_city.append({"city": city, "restaurants": restaurants})
            new_errors = errors[errors_before:]
            if restaurants:
                print(f"    - [{city}] 맛집 {len(restaurants)}곳 검색 완료")
            elif new_errors and new_errors[-1]["type"] == "AUTH_ERROR":
                print(f"    - [{city}] 오류: 인증 실패. 키 설정을 확인하세요. '데이터 없음'으로 처리합니다.")
            elif new_errors and new_errors[-1]["type"] == "EMPTY_RESULT":
                print(f"    - [{city}] 검색 결과 0건(다음 단계로 진행)")
            else:
                print(f"    - [{city}] 맛집 검색 실패. '데이터 없음'으로 처리합니다.")

        first_recommendation_ok = not any(e["step"] == "first_recommendation" for e in errors)
        if first_recommendation_ok:
            redis_cache_manager.set(
                date_str, {"recommended": first_json, "restaurants_by_city": restaurants_by_city}
            )

    print("[3/3] 최종 리포트 생성 중(LLM)...")
    cities = [c.get("city") for c in first_json.get("recommended_cities", [])]
    span = trace.span(name="report_generation", input={"cities": cities})
    report_md = call_final_report(date_str, first_json, restaurants_by_city, errors, span=span)
    span.end(output=report_md)
    print("    - 리포트 생성 완료")

    trace.update(output={"errors": errors})
    langfuse_client.flush()

    json_path, md_path = save_results(date_str, first_json, restaurants_by_city, errors, report_md)
    print(f"\n완료! {md_path} 를 확인하세요.")
    print(f"원본 데이터: {json_path}")


if __name__ == "__main__":
    main()
