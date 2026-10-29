"""Database configuration and initialization."""

from sqlalchemy import inspect, text

from .database import Base, SessionLocal, engine, get_db


def _remove_legacy_employee_code_unique_index() -> None:
    if engine.dialect.name != "mysql":
        return

    inspector = inspect(engine)
    index_names = set()
    for constraint in inspector.get_unique_constraints("agents"):
        if constraint.get("column_names") == ["employee_code"] and constraint.get("name"):
            index_names.add(constraint["name"])
    for index in inspector.get_indexes("agents"):
        if index.get("unique") and index.get("column_names") == ["employee_code"] and index.get("name"):
            index_names.add(index["name"])

    for index_name in index_names:
        quoted_name = engine.dialect.identifier_preparer.quote(index_name)
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE agents DROP INDEX {quoted_name}"))


def init_db() -> None:
    from .. import models  # noqa: F401 - register model tables before creating them

    Base.metadata.create_all(bind=engine)
    _remove_legacy_employee_code_unique_index()


__all__ = ["Base", "SessionLocal", "engine", "get_db", "init_db"]
