"""로컬 Redis 기반 결과 캐시(1차 추천 + 맛집 검색 결과, TTL 1시간).

같은 -date로 재실행할 때 LLM/지도 API 호출을 건너뛰고 캐시된 데이터로 리포트만
다시 생성하기 위한 캐시다. Redis 장애/미기동 시에도 전체 파이프라인이 절대
영향받지 않도록, 캐시 조회/저장 실패는 여기서 흡수하고 캐시 미스로 처리한다.
"""

import json
import logging
import threading

import redis

from project_config.settings import settings

logger = logging.getLogger(__name__)


def _cache_key(date_str: str) -> str:
    return f"travel_planner:cache:{date_str}"


class RedisCacheManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._client = None
        return cls._instance

    def _get_client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = redis.Redis(
                        host=settings.redis_host,
                        port=settings.redis_port,
                        db=settings.redis_db,
                        decode_responses=True,
                        socket_connect_timeout=2,
                        socket_timeout=2,
                    )
        return self._client

    def get(self, date_str: str):
        try:
            raw = self._get_client().get(_cache_key(date_str))
        except redis.exceptions.RedisError as e:
            logger.warning("Redis 캐시 조회 실패::NoOp 로 대체::%s", e)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Redis 캐시 데이터 파싱 실패::캐시 미스로 처리::%s", e)
            return None

    def set(self, date_str: str, data: dict) -> None:
        try:
            self._get_client().set(
                _cache_key(date_str),
                json.dumps(data, ensure_ascii=False),
                ex=settings.cache_ttl_seconds,
            )
        except redis.exceptions.RedisError as e:
            logger.warning("Redis 캐시 저장 실패::캐시 없이 계속 진행::%s", e)


redis_cache_manager = RedisCacheManager()
