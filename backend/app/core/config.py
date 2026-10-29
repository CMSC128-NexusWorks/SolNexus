from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Comma-separated browser origins allowed to call the API with the session cookie.
    cors_origins: str = "http://localhost:5173"
    # Browsers accept Secure cookies on http://localhost, except Safari; set false only for that case.
    session_cookie_secure: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
