from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfiguracja przez zmienne srodowiskowe (zasada najmniejszych uprawnien).

    Klucze API NIGDY nie trafiaja do repozytorium - tylko menedzer sekretow/env.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AIRALERT_")

    app_name: str = "AirAlert Monitor"
    environment: str = "local"  # local | staging | prod

    database_url: str = "sqlite:///./airalert.db"

    # Anti-spoofing: wymagaj zgodnosci domeny z rejestrem zrodla
    strict_domain_pin: bool = True

    # Progi swiezosci danych
    stale_after_minutes: int = 60

    # Powiadomienia
    notification_merge_window_s: int = 300
    notification_max_per_hour_per_subscription: int = 10
    loud_alerts_official_only: bool = True  # glosne alarmy TYLKO dla oficjalnych

    # Admin
    admin_api_token: str = ""  # pusty => endpointy administracyjne zablokowane
    fcm_server_key: str = ""

    # Sekret szyfrowania tokenow push - NALEZY nadpisac w produkcji (menedzer sekretow)
    push_token_secret: str = "change-me-dev-only"

    # CORS - originy frontendu dozwolone w przegladarce (JSON array w env)
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
