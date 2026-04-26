import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(Path(__file__).parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")
    # Trading mode
    MODE: str = Field(default="PAPER")

    # Active assets
    ACTIVE_ASSETS: str = Field(default="XRP,EURUSD")

    # Coinbase Advanced Trade
    COINBASE_API_KEY: str = Field(default="")
    COINBASE_SECRET: str = Field(default="")

    # MetaTrader 5
    MT5_LOGIN: int = Field(default=0)
    MT5_PASSWORD: str = Field(default="")
    MT5_SERVER: str = Field(default="")

    # Database
    DB_URL: str = Field(
        default="postgresql://trader:secret@localhost:5432/trading"
    )

    # Telegram
    TELEGRAM_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")

    # Risk
    MAX_DRAWDOWN: float = Field(default=0.10)
    RISK_PER_TRADE: float = Field(default=0.01)
    MAX_DAILY_LOSS: float = Field(default=0.05)
    MAX_CONCURRENT_POSITIONS: int = Field(default=3)

    # Strategy
    PANIC_DROP_THRESHOLD: float = Field(default=-0.03)
    RSI_OVERSOLD: float = Field(default=30.0)
    VOLUME_SPIKE_MULTIPLIER: float = Field(default=2.0)
    OB_IMBALANCE_THRESHOLD: float = Field(default=0.60)
    MIN_SIGNAL_SCORE: int = Field(default=5)
    TAKE_PROFIT_PCT: float = Field(default=0.02)
    STOP_LOSS_PCT: float = Field(default=0.015)

    # API
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)

    # Dashboard
    DASHBOARD_PORT: int = Field(default=8501)

    @property
    def is_live(self) -> bool:
        return self.MODE == "LIVE"

    @property
    def is_paper(self) -> bool:
        return self.MODE == "PAPER"

    @property
    def asset_list(self) -> list[str]:
        return [a.strip() for a in self.ACTIVE_ASSETS.split(",")]



settings = Settings()
