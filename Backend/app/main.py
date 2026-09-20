from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import audit, auth, changes, day_overrides, schedules, users,tasks, task_comments, tickets

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(task_comments.router)
    app.include_router(tasks.router)
    app.include_router(day_overrides.router)
    app.include_router(users.router)
    app.include_router(auth.router)
    app.include_router(schedules.router)
    app.include_router(changes.router)
    app.include_router(audit.router)
    app.include_router(tickets.router)

    @app.get("/api/v1/health", tags=["Sistema"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

app = create_app()