from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "openai"
    llm_model_main: str = ""  # planner, scriptwriter, editor, designer
    llm_model_fast: str = ""  # small/fast calls
    llm_timeout_seconds: float = 90
    llm_validation_retries: int = 2
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Icon library (Phase 4)
    icon_image_model: str = "gpt-image-1.5"
    icon_image_quality: str = "medium"  # low | medium | high
    icon_image_timeout_seconds: float = 120
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    icon_max_new_per_video: int = 3
    icon_search_k: int = 8
    icon_search: str = "numpy"  # numpy (works anywhere) | atlas (Atlas Vector Search)
    model_prices: str = ""  # JSON override of app/pricing.py, e.g. {"gpt-5.5": [5, 30]}

    mongodb_uri: str = ""
    mongodb_db: str = "vidgen"

    tts_provider: str = "edge"
    tts_voice: str = "en-US-AndrewNeural"
    # Falls back to HTTPS_PROXY for providers that ignore env proxies.
    tts_proxy: str | None = None
    google_application_credentials: str = ""
    elevenlabs_api_key: str = ""

    render_service_url: str = "http://localhost:3100"
    media_dir: Path = Path("./media")
    public_base_url: str = "http://localhost:8000"
    # Phase 5: parallel scenes, live stream, reliability
    llm_concurrency: int = 4  # designer calls at once
    tts_concurrency: int = 3
    render_concurrency: int = 2  # fallback; the render service's /health value wins
    hls_segment_seconds: int = 4
    ffmpeg_timeout_seconds: float = 180
    watchdog_stall_seconds: int = (
        300  # no progress for this long -> job failed "stalled"
    )
    watchdog_interval_seconds: float = 30
    alive_interval_seconds: float = (
        15  # a running process ticks job.alive_at this often
    )
    resume_after_seconds: float = 45  # alive_at older than this -> the process died

    cors_origins: list[str] = ["http://localhost:5173"]

    # Accounts and limits (Phase 7)
    auth_secret: str = ""  # signs session cookies; empty = random per process (sessions end on restart)
    session_days: int = 7
    cookie_secure: bool = False  # set true when served over HTTPS
    # Videos per rolling 30 days and at once come from the plan (app/billing/plans.py).
    admin_unlimited: bool = True  # the admin (first account) is not rate limited

    # Email (password reset links). Without SMTP_USERNAME the link is written to the server log.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587  # 587 = STARTTLS, 465 = SSL
    smtp_username: str = ""  # e.g. you@gmail.com
    smtp_password: str = ""  # a Google App Password, not your Gmail password
    mail_from: str = ""  # defaults to SMTP_USERNAME
    smtp_timeout_seconds: float = 20
    app_base_url: str = (
        "http://localhost:5173"  # where links in emails point (the web app)
    )
    password_reset_minutes: int = 30

    # Stripe (memberships). Use a test-mode or sandbox key while developing; a restricted key
    # (rk_...) needs write access to Checkout Sessions and read access to PaymentIntents and Charges.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = (
        ""  # whsec_..., from `stripe listen` or the Dashboard endpoint
    )
    stripe_proxy: str | None = None  # falls back to HTTPS_PROXY


settings = Settings()
