import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models import User

# In-memory SQLite database for testing.
# StaticPool keeps one shared connection so all threads see the same DB.
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _point_background_sessions():
    """Redirect the service-layer session factory (used by background scan
    tasks, which open their own sessions outside the request scope) to the
    test database."""
    from app.services import alert_service

    alert_service.session_factory = TestingSessionLocal
    yield


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function", autouse=True)
def _reset_login_rate_limiter():
    """Reset the in-memory login rate limiter between tests so one test's
    attempts never exhaust another test's budget (all tests share the
    'testclient' IP)."""
    from app.api.v1.endpoints.auth import login_limiter

    login_limiter.reset()
    yield
    login_limiter.reset()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a TestClient that overrides the get_db dependency to use the test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client, db_session):
    """Register + login a user and return bearer auth headers."""
    client.post(
        "/api/v1/register",
        json={"username": "analyst1", "email": "analyst1@example.com", "password": "secret123", "role": "ANALYST"},
    )
    resp = client.post(
        "/api/v1/login",
        data={"username": "analyst1", "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_headers(client, db_session):
    # Register a normal analyst first, then promote to ADMIN in the DB directly
    # (self-registration is ABAC-restricted to USER/ANALYST roles).
    client.post(
        "/api/v1/register",
        json={"username": "admin1", "email": "admin1@example.com", "password": "secret123", "role": "ANALYST"},
    )
    admin = db_session.query(User).filter(User.username == "admin1").first()
    admin.role = "ADMIN"
    admin.clearance_level = 4
    db_session.commit()

    resp = client.post(
        "/api/v1/login",
        data={"username": "admin1", "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
