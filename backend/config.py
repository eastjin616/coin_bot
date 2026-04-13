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
    groq_api_key: str = ""

    # 기술적 지표 전략 파라미터 (일봉 RSI 단독)
    rsi_buy_threshold: float = 35.0   # RSI 이하 → 매수 (일봉 백테스팅 최적값)
    rsi_sell_threshold: float = 55.0  # RSI 이상 → 매도 (일봉 백테스팅 최적값)

    # 기능 플래그
    enable_volatility_filter: bool = True

    # 운영 설정
    cooldown_minutes: int = 5
    poll_interval_seconds: int = 60  # 1분마다 순회

    # 예산
    stock_budget_krw: int = 50000
    coin_budget_krw: int = 50000

    # 리스크 관리
    order_size_ratio: float = 0.5
    risk_on_order_size_ratio: float = 0.2
    caution_order_size_ratio: float = 0.1
    risk_off_order_size_ratio: float = 0.05
    min_order_amount_krw: int = 10000
    max_order_amount_krw: int = 50000
    target_position_budget_krw: int = 50000
    stop_loss_percent: float = 5.0
    take_profit_percent: float = 0.0
    max_hold_days: int = 10
    time_stop_min_pnl_pct: float = 0.0
    weak_trend_rsi_buffer: float = 7.0
    live_derating_enabled: bool = True
    live_derating_lookback_days: int = 30
    live_derating_min_sell_count: int = 3
    live_derating_min_win_rate_pct: float = 40.0
    live_derating_min_avg_pnl_pct: float = -0.5
    loss_streak_cooldown_enabled: bool = True
    loss_streak_threshold: int = 2
    loss_streak_cooldown_days: int = 7
    loss_streak_lookback_days: int = 30
    manual_holding_policy: str = "alert_only"
    manual_holding_min_value_krw: int = 10000

    # 운영 리스크 캡 (0이면 비활성화)
    max_open_positions: int = 12
    max_buys_per_day: int = 48

    # (미사용) 대시보드 인증 & CORS
    dashboard_api_key: str = ""
    vercel_origin: str = "http://localhost:3000"

    @property
    def allowed_chat_ids(self) -> List[int]:
        """허용된 텔레그램 chat_id 목록을 정수 리스트로 반환"""
        return [int(cid.strip()) for cid in self.telegram_allowed_chat_ids.split(",") if cid.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
