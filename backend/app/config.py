from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LTA_")

    database_url: str = "sqlite:///./data/trader_analyzer.db"
    data_dir: Path | None = None
    upload_dir: Path = Path("./data/uploads")
    pnl_tolerance: str = "0.01"
    parser_confidence_threshold: float = 0.5
    parser_ambiguous_margin: float = 0.15
    preview_sample_size: int = 10
    upload_retention_hours: float = 24.0
    analytics_timezone: str = "America/New_York"
    breakeven_tolerance: str = "0.01"

    # Step 10 — automation / journal / backup
    file_stable_seconds: float = 2.0
    inbox_debounce_seconds: float = 5.0
    auto_process_inbox: bool = True
    eod_finalize_enabled: bool = True
    eod_finalize_hour: int = 20
    eod_finalize_minute: int = 15
    automatic_backup: bool = True
    backup_retain_daily: int = 30
    backup_retain_weekly: int = 12
    watcher_poll_seconds: float = 2.0
    schema_version: str = "10"
    app_version: str = "0.10.0"

    # Market data (Step 4)
    market_data_provider: str = "none"  # none | alpaca | fake
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    alpaca_data_feed: str = "iex"  # sip | iex
    market_benchmark: str = "SPY"
    market_adjustment_mode: str = "raw"
    market_lookback_calendar_days: int = 120
    intraday_store_raw_payload: bool = False

    # Step 5 — signal matching
    signal_auto_match_seconds: int = 90
    signal_manual_match_before_seconds: int = 30
    signal_manual_match_after_seconds: int = 180
    signal_prefer_realtime: bool = True

    # Step 7 — risk
    loss_beyond_r_threshold: str = "-1.05"

    # Step 9 — research lab
    research_min_sample: int = 10
    research_min_correlation_n: int = 10
    research_max_groups: int = 200
    research_bootstrap_seed: int = 20260902
    research_bootstrap_iterations: int = 2000
    research_statistics_version: str = "1"
    research_heatmap_ticker_top_n: int = 20

    # Deployment
    cors_origins: str = ""
    disable_automation: bool = False

    @property
    def sync_database_url(self) -> str:
        return self.database_url

    def resolved_cors_origins(self) -> list[str]:
        if self.cors_origins.strip():
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:8765",
            "http://127.0.0.1:8765",
        ]


settings = Settings()
