"""Test fixtures.

Each test module gets a fresh in-memory SQLite database with a StaticPool,
so the TestClient's connection and the fixture's connection see the same
data without touching the developer's savora.db.
"""
import os

os.environ.setdefault("GEMINI_API_KEY", "")  # force the offline path in CI
os.environ.setdefault("GROQ_API_KEY", "")             # no live LLM calls in CI
os.environ.setdefault("EMBEDDING_PROVIDER", "none")   # never load a model in tests
os.environ.setdefault("LLM_PROVIDER", "none")         # each test opts in explicitly

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import MenuItem, User, UserRole

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _database():
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    db.add_all(
        [
            User(
                email="admin@savora.in",
                full_name="Admin",
                hashed_password=hash_password("admin123"),
                role=UserRole.ADMIN,
            ),
            User(
                email="customer@savora.in",
                full_name="Customer",
                hashed_password=hash_password("customer123"),
                role=UserRole.CUSTOMER,
            ),
            User(
                email="other@savora.in",
                full_name="Other Customer",
                hashed_password=hash_password("customer123"),
                role=UserRole.CUSTOMER,
            ),
        ]
    )
    seed_items = [
        ("Chole Masala", "Chickpeas stewed hot and tangy", "Main Course", 200, ["vegetarian", "spicy"]),
        ("Dal Tadka", "Yellow lentils, gentle spices", "Main Course", 180, ["vegetarian"]),
        ("Butter Chicken", "Rich tomato and cashew gravy", "Main Course", 380, ["non-vegetarian", "contains-nuts"]),
        ("Crispy Corn", "Sweet corn deep-fried till crunchy", "Starters", 180, ["vegetarian"]),
        ("Tomato Shorba", "Clear light tomato broth, steamed and grilled sides", "Starters", 140, ["vegetarian", "vegan"]),
        ("Sold Out Special", "Currently unavailable dish", "Main Course", 150, ["vegetarian"]),
    ]
    for name, description, category, price, tags in seed_items:
        item = MenuItem(
            name=name,
            description=description,
            category=category,
            price=price,
            is_available=name != "Sold Out Special",
        )
        item.tags = tags
        db.add(item)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _auth_header(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return _auth_header(client, "admin@savora.in", "admin123")


@pytest.fixture
def customer_headers(client: TestClient) -> dict[str, str]:
    return _auth_header(client, "customer@savora.in", "customer123")


@pytest.fixture
def other_customer_headers(client: TestClient) -> dict[str, str]:
    return _auth_header(client, "other@savora.in", "customer123")


@pytest.fixture
def db_session():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
