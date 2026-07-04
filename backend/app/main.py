from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api import project_router, search_router
from app.core.database import engine
from app.errors import DomainError
from app.models import Base


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="ResearchCode-Agent", lifespan=lifespan)
app.include_router(project_router, prefix="/api/projects", tags=["projects"])
app.include_router(search_router, prefix="/api", tags=["search"])


@app.exception_handler(DomainError)
async def domain_error_handler(_: object, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
