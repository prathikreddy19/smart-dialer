from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .api.database import router as database_router
from .api.dialer import router as dialer_router
from .api.health import router as health_router
from .api.upload import router as upload_router
from .core.logging_config import configure_logging
from .database import init_db

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Smart Dialer API", lifespan=lifespan)
app.include_router(health_router)
app.include_router(upload_router)
app.include_router(database_router)
app.include_router(dialer_router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request, _exc: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Database operation failed."})
