import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv(Path(__file__).parent.parent / ".env")


class Settings(BaseSettings):
    # Trading mode
    MODE: str = Field(default="PAPER", env="MODE")

    # Active assets
    ACTIVE_ASSETS: str = Field(default="XRP,EURUSD", env="ACTIVE_ASSETS")

    # Binance
    BINANCE_API_KEY: str = Field(default="", env="BINANCE_API_KEY")
    BINANCE_SECRET: str = Field(default="", env="BINANCE_SECRET")

    # MetaTrader 5
    MT5_LOGIN: int = Field(default=0, env="MT5_LOGIN")
    MT5_PASSWORD: str = Field(default="", env="MT5_PASSWORD")
    MT5_SERVER: str = Field(default="", env="MT5_SERVER")

    # Database
    DB_URL: str = Field(
        default="postgresql://trader:secret@localhost:5432/trading", env="DB_URL"
    )

    # Telegram
    TELEGRAM_TOKEN: str = Field(default="", env="TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID: str = Field(default="", env="TELEGRAM_CHAT_ID")

    # Risk
    MAX_DRAWDOWN: float = Field(default=0.10, env="MAX_DRAWDOWN")
    RISK_PER_TRADE: float = Field(default=0.01, env="RISK_PER_TRADE")
    MAX_DAILY_LOSS: float = Field(default=0.05, env="MAX_DAILY_LOSS")
    MAX_CONCURRENT_POSITIONS: int = Field(default=3, env="MAX_CONCURRENT_POSITIONS")

    # Strategy
    PANIC_DROP_THRESHOLD: float = Field(default=-0.03, env="PANIC_DROP_THRESHOLD")
    RSI_OVERSOLD: float = Field(default=30.0, env="RSI_OVERSOLD")
    VOLUME_SPIKE_MULTIPLIER: float = Field(default=2.0, env="VOLUME_SPIKE_MULTIPLIER")
    OB_IMBALANCE_THRESHOLD: float = Field(default=0.60, env="OB_IMBALANCE_THRESHOLD")
    MIN_SIGNAL_SCORE: int = Field(default=5, env="MIN_SIGNAL_SCORE")
    TAKE_PROFIT_PCT: float = Field(default=0.02, env="TAKE_PROFIT_PCT")
    STOP_LOSS_PCT: float = Field(default=0.015, env="STOP_LOSS_PCT")

    # API
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")

    # Dashboard
    DASHBOARD_PORT: int = Field(default=8501, env="DASHBOARD_PORT")

    @property
    def is_live(self) -> bool:
        return self.MODE == "LIVE"

    @property
    def is_paper(self) -> bool:
        return self.MODE == "PAPER"

    @property
    def asset_list(self) -> list[str]:
        return [a.strip() for a in self.ACTIVE_ASSETS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
