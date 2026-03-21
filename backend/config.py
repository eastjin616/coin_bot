from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://user:password@localhost:5432/coinbot"

    # 주식 - 미래에셋증권
    mirae_asset_app_key: str = ""
    mirae_asset_app_secret: str = ""
    mirae_asset_account: str = ""

    # 코인 - 업비트
    upbit_access_key: str = ""
    upbit_secret_key: str = ""

    # 텔레그램
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = "123456789"

    # AI 모델 (없으면 랜덤 예측 모드)
    vision_model_path: str = ""

    # LLM API 키 (차트 분석용)
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # 신호 임계값
    signal_buy_threshold: float = 80.0
    signal_sell_threshold: float = 20.0

    # 운영 설정
    cooldown_minutes: int = 5
    poll_interval_seconds: int = 60

    # 예산
    stock_budget_krw: int = 50000
    coin_budget_krw: int = 50000

    # 리스크 관리
    order_size_ratio: float = 0.5
    stop_loss_percent: float = 5.0
    take_profit_percent: float = 10.0

    @property
    def allowed_chat_ids(self) -> List[int]:
        """허용된 텔레그램 chat_id 목록을 정수 리스트로 반환"""
        return [int(cid.strip()) for cid in self.telegram_allowed_chat_ids.split(",") if cid.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
