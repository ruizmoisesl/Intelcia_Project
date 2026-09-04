from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración central (variables de entorno / .env)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Portal de Gestión Empresarial"
    DEBUG: bool = True

    # Seguridad / JWT
    SECRET_KEY: str  # obligatoria: la app no arranca sin ella
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 horas

    # Base de datos: SQLite en dev; cambiar solo esta variable para Postgres/MySQL.
    DATABASE_URL: str = "sqlite:///./portal.db"

    # CORS (frontend Astro en :4321)
    ALLOWED_ORIGINS: list[str] = ["http://localhost:4321"]

    # Festivos oficiales vía Google Calendar API.
    # API key de un proyecto de Google Cloud con la Calendar API habilitada
    # (suficiente para el calendario público de festivos; sin OAuth).
    GOOGLE_CALENDAR_API_KEY: str | None = None
    GOOGLE_CALENDAR_ID: str = "es.colombian#holiday@group.v.calendar.google.com"
    # auto: Google con fallback local · google: solo Google · local: nunca consulta
    HOLIDAYS_PROVIDER: str = "auto"
    HOLIDAYS_CACHE_TTL_HOURS: int = 24

    # Zona horaria del negocio: «hoy» se calcula aquí, no con la TZ del servidor.
    BUSINESS_TIMEZONE: str = "America/Bogota"


settings = Settings()