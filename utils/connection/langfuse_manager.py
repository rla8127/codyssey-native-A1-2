"""단일 Langfuse 클라이언트 관리(프로그램 전체가 하나의 클라이언트를 공유).

Langfuse 서버 장애/미기동/미설정 시에도 여행 리포트 생성 로직이 절대 영향받지
않도록, 클라이언트 생성 실패는 여기서 흡수하고 NoOp 클라이언트로 대체한다.
"""

import logging
import threading

from langfuse import Langfuse

from project_config.settings import settings

logger = logging.getLogger(__name__)


class _NoOpStatefulClient:
    """Langfuse 미가동/미설정 시 사용하는 더미 trace/span/generation."""

    def __getattr__(self, _name):
        return self

    def __call__(self, *args, **kwargs):
        return self


class LangfuseClientManager:
    _instance = None
    _lock = threading.Lock()
    _noop_client = _NoOpStatefulClient()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._client = None
        return cls._instance

    def get_client(self):
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return self._noop_client
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        self._client = Langfuse(
                            public_key=settings.langfuse_public_key,
                            secret_key=settings.langfuse_secret_key,
                            host=settings.langfuse_host,
                            timeout=settings.langfuse_timeout_seconds,
                            max_retries=settings.langfuse_max_retries,
                            enabled=settings.langfuse_tracing_enabled,
                        )
                    except Exception:
                        logger.warning("Langfuse 클라이언트 생성 실패::NoOp 로 대체", exc_info=True)
                        self._client = self._noop_client
        return self._client


langfuse_manager = LangfuseClientManager()
