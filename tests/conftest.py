import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest

from app.database.database import Base, engine
from app import models  # noqa: F401


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
