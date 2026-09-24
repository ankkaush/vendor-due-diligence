"""Application configuration, read from the environment (.env locally).

Grows incrementally, phase by phase, as each component needs new settings —
Phase 4 added database_url; Phase 9 added the review UI's single-reviewer
auth credentials and the key CSRF tokens are signed with (deployment.md:
"single-reviewer basic auth for the review interface," security.md's CSRF
requirement); Phase 10 adds Langfuse/Sentry credentials, both optional —
every field here defaults to empty/unconfigured, which is exactly what
makes app.observability's tracing/error-reporting a no-op until someone
actually sets real values (no account required to build or test Phase 10).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vendor_dd:local_dev_only_not_a_real_secret@localhost:5437/vendor_dd"

    # Local dev defaults only — real values are set via the platform secret
    # manager in production (security.md), never committed here. Field
    # names match .env.example's pre-existing REVIEWER_USERNAME/
    # REVIEWER_PASSWORD/APP_SECRET_KEY, anticipated back in Phase 2.
    reviewer_username: str = "reviewer"
    reviewer_password: str = "local_dev_only_not_a_real_secret"
    app_secret_key: str = "local_dev_only_not_a_real_secret_app_key"

    app_env: str = "development"

    # Optional — app.observability.py no-ops on every one of these unset.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    sentry_dsn: str = ""


settings = Settings()
