from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import my_api


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test_students.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine)

    my_api.Base.metadata.create_all(bind=engine)
    my_api.users_db.clear()
    my_api.tokens_db.clear()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    my_api.app.dependency_overrides[my_api.get_db] = override_get_db

    with TestClient(my_api.app) as test_client:
        yield test_client

    my_api.app.dependency_overrides.clear()
    my_api.users_db.clear()
    my_api.tokens_db.clear()
    my_api.Base.metadata.drop_all(bind=engine)


def register_user(client: TestClient, username: str, password: str, role: str = "reader"):
    return client.post(
        "/auth/register",
        json={"username": username, "password": password, "role": role},
    )


def login_user(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_student_payload(**overrides):
    payload = {
        "last_name": "Ivanov",
        "first_name": "Ivan",
        "faculty": "Physics",
        "course": "Quantum Mechanics",
        "grade": 91.5,
    }
    payload.update(overrides)
    return payload


def create_admin_and_token(client: TestClient) -> str:
    register_response = register_user(client, "admin", "adminpass", "admin")
    assert register_response.status_code == 201
    return login_user(client, "admin", "adminpass")


def test_register_user_success(client: TestClient):
    response = register_user(client, "new_user", "secret", "reader")

    assert response.status_code == 201
    assert "new_user" in response.json()["message"]


def test_register_user_duplicate_returns_400(client: TestClient):
    first_response = register_user(client, "duplicate_user", "secret", "reader")
    second_response = register_user(client, "duplicate_user", "secret", "reader")

    assert first_response.status_code == 201
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Пользователь с таким именем уже существует"


def test_login_returns_token_for_valid_credentials(client: TestClient):
    register_user(client, "reader", "readerpass", "reader")

    response = client.post("/auth/login", data={"username": "reader", "password": "readerpass"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_invalid_password(client: TestClient):
    register_user(client, "reader", "readerpass", "reader")

    response = client.post("/auth/login", data={"username": "reader", "password": "wrongpass"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверное имя пользователя или пароль"


def test_create_student_as_admin(client: TestClient):
    token = create_admin_and_token(client)

    response = client.post(
        "/students",
        json=create_student_payload(),
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["first_name"] == "Ivan"
    assert body["faculty"] == "Physics"


def test_create_student_forbidden_for_reader(client: TestClient):
    register_user(client, "reader", "readerpass", "reader")
    token = login_user(client, "reader", "readerpass")

    response = client.post(
        "/students",
        json=create_student_payload(),
        headers=auth_headers(token),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав. Требуется роль 'admin'."


def test_get_students_returns_created_students(client: TestClient):
    token = create_admin_and_token(client)
    client.post("/students", json=create_student_payload(first_name="Ivan"), headers=auth_headers(token))
    client.post("/students", json=create_student_payload(first_name="Petr"), headers=auth_headers(token))

    response = client.get("/students", headers=auth_headers(token))

    assert response.status_code == 200
    students = response.json()
    assert len(students) == 2
    assert {student["first_name"] for student in students} == {"Ivan", "Petr"}


def test_get_students_requires_authorization(client: TestClient):
    response = client.get("/students")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_student_by_id_returns_student(client: TestClient):
    token = create_admin_and_token(client)
    create_response = client.post(
        "/students",
        json=create_student_payload(first_name="Sergey"),
        headers=auth_headers(token),
    )
    student_id = create_response.json()["id"]

    response = client.get(f"/students/{student_id}", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["first_name"] == "Sergey"


def test_get_student_by_id_returns_404_for_missing_student(client: TestClient):
    token = create_admin_and_token(client)

    response = client.get("/students/9999", headers=auth_headers(token))

    assert response.status_code == 404
    assert response.json()["detail"] == "Студент не найден"
