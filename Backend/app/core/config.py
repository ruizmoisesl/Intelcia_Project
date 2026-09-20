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

        # ── Jira (Cloud): envío de tareas ──
    JIRA_BASE_URL: str | None = None      # https://tuempresa.atlassian.net
    JIRA_EMAIL: str | None = None
    JIRA_API_TOKEN: str | None = None     # Atlassian → Cuenta → Seguridad → Token de API
    JIRA_PROJECT_KEY: str | None = None   # el proyecto debe tener tipo de issue «Task»

    # ── Trello: envío de tareas ──
    TRELLO_KEY: str | None = None
    TRELLO_TOKEN: str | None = None
    TRELLO_LIST_ID: str | None = None     # ID de la lista destino

    # ── Adjuntos de comentarios ──
    UPLOADS_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 5
    
        # ── Correo (Gmail SMTP) ──
    # Gmail REQUIERE contraseña de aplicación (cuenta con 2FA activado):
    #   https://myaccount.google.com/apppasswords  → 16 caracteres.
    # El password normal de la cuenta NO funciona con SMTP.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587          # 587 = STARTTLS · 465 = SSL (automático)
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None  # p. ej. "Portal de Gestión <portal@empresa.com>"
    NOTIFICATIONS_ENABLED: bool = True  # kill-switch general de correos

    # URL pública para los enlaces dentro de los correos.
    APP_BASE_URL: str = "http://localhost:4321"

    # ── Recordatorio semanal de turno (viernes) ──
    WEEKLY_REMINDER_ENABLED: bool = True
    WEEKLY_REMINDER_WEEKDAY: int = 4   # 0=lunes … 4=viernes
    WEEKLY_REMINDER_HOUR: int = 8      # a partir de esta hora (zona negocio)

        # ── Tickets: mesón de soporte en Jira (LECTURA) ──
    JIRA_TICKETS_PROJECT: str | None = None   # p. ej. "SOP" (puede diferir del de Tareas)
    TICKETS_CACHE_TTL_SECONDS: int = 60
    TICKETS_MAX_RESULTS: int = 500

        # ── Tickets: ámbito del mesón (empresa global → solo ESTA sede/grupo) ──
    # Gana el primero configurado de: EXTRA_JQL > FIELD_ID/VALUE > GROUP.
    JIRA_TICKETS_EXTRA_JQL: str | None = None          # A: fragmento JQL crudo
    JIRA_TICKETS_FIELD_ID: str | None = None           # B: campo anclado → cf[id]
    JIRA_TICKETS_FIELD_VALUE: str | None = None        #    = "valor"
    JIRA_TICKETS_GROUP: str | None = None              # C: grupo → membersOf("…")
    JIRA_TICKETS_INCLUDE_UNASSIGNED: bool = True       #    incluir la cola sin asignar

    # ── KPIs del mesón ──
    JIRA_TICKETS_SLA_RISK_JQL: str | None = None       # ej. (JSM): "Time to resolution" < remaining("2h")
    JIRA_TICKETS_MTTR_WINDOW_DAYS: int = 30
    JIRA_TICKETS_CSAT_FIELD: str | None = None         # ej. customfield_10041
    TICKETS_STATS_CACHE_TTL_SECONDS: int = 300

settings = Settings()