"""환경변수 및 .env 파일 기반 설정을 관리하는 모듈."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 실제 배포 환경의 환경변수가 .env 파일 값보다 우선하도록, override 없이 먼저 로드한다.
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    kakao_rest_api_key: str = ""

    langfuse_host: str = "http://192.168.10.20:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_tracing_enabled: bool = True
    langfuse_timeout_seconds: int = 5
    langfuse_max_retries: int = 1

    config_dir: Path = PROJECT_ROOT / "project_config"
    results_dir: Path = PROJECT_ROOT / "results"


def get_settings() -> Settings:
    """테스트에서 monkeypatch로 대체하기 쉽도록 인스턴스 생성을 팩토리 함수로 분리한다."""
    return Settings()


settings = get_settings()
