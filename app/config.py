"""Application configuration, read from the environment (.env locally).

Deliberately minimal for Phase 4 — only what the data model and its
migrations/tests need. Grows in later phases as each component needs new
settings, per the phase plan (no speculative config for things that don't
exist yet).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vendor_dd:local_dev_only_not_a_real_secret@localhost:5437/vendor_dd"


settings = Settings()
