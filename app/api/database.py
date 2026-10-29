from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .. import models  # noqa: F401 - register all ORM tables before reset
from ..database.database import Base, engine

router = APIRouter(prefix="/database", tags=["Database"])


@router.post("/reset")
def reset_database():
    try:
        # Reset is intentionally destructive in this prototype. Recreate tables
        # from ORM metadata so an old schema cannot retain required legacy fields.
        with engine.connect() as connection:
            is_mysql = engine.dialect.name == "mysql"
            if is_mysql:
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            try:
                Base.metadata.drop_all(bind=connection)
                Base.metadata.create_all(bind=connection)
            finally:
                if is_mysql:
                    # FK checks are connection scoped; always restore them.
                    connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
                connection.commit()
        return {
            "status": "success",
            "message": "Database reset and tables recreated from the current models.",
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database reset failed.") from exc
