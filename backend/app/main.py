from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import require_staff
from app.auth.router import router as auth_router
from app.core.config import settings
from app.errors import install_error_handlers

app = FastAPI(title="SolNexus API")
install_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "solnexus-api",
        "database_configured": "true" if settings.database_url else "false",
    }


app.include_router(auth_router, prefix="/api/v1")

# Every feature endpoint requires a signed-in staff member (FR-10, NFR-03). Add feature routers to
# `protected` with protected.include_router(...) above the app.include_router(protected) line.
protected = APIRouter(prefix="/api/v1", dependencies=[Depends(require_staff)])
app.include_router(protected)
