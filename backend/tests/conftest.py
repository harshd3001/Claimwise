import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    application = create_app("sqlite:///:memory:")
    with TestClient(application) as test_client:
        yield test_client


def identity(user_id: str = "employee-demo") -> dict[str, str]:
    return {"X-Demo-User-ID": user_id}


def sample_claim(**overrides):
    values = {
        "merchant": "  Metro Cafe  ",
        "category": "Meals",
        "description": "Client meeting lunch",
        "expense_date": "2026-10-28",
        "amount_paise": 12500,
    }
    values.update(overrides)
    return values
