"""Auth, role guards, and menu CRUD."""


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_returns_token_and_role(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@savora.in", "password": "admin123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "admin"
    assert body["access_token"]


def test_login_rejects_wrong_password_without_leaking_which_field(client):
    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "admin@savora.in", "password": "nope"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "ghost@savora.in", "password": "nope"},
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_register_creates_customer_and_blocks_admin_escalation(client):
    ok = client.post(
        "/api/auth/register",
        json={
            "email": "new@savora.in",
            "full_name": "New Person",
            "password": "secret123",
        },
    )
    assert ok.status_code == 201
    assert ok.json()["user"]["role"] == "customer"

    escalation = client.post(
        "/api/auth/register",
        json={
            "email": "sneaky@savora.in",
            "full_name": "Sneaky",
            "password": "secret123",
            "role": "admin",
        },
    )
    assert escalation.status_code == 403


def test_duplicate_registration_conflicts(client):
    payload = {
        "email": "dupe@savora.in",
        "full_name": "Dupe",
        "password": "secret123",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_menu_read_is_public_and_hides_unavailable(client):
    response = client.get("/api/menu")
    assert response.status_code == 200
    names = [i["name"] for i in response.json()]
    assert "Dal Tadka" in names
    assert "Sold Out Special" not in names


def test_admin_can_see_unavailable_items(client, admin_headers):
    response = client.get("/api/menu", params={"available_only": False}, headers=admin_headers)
    names = [i["name"] for i in response.json()]
    assert "Sold Out Special" in names


def test_menu_write_requires_admin(client, customer_headers):
    payload = {
        "name": "Rogue Dish",
        "description": "x",
        "category": "Main Course",
        "price": 100,
        "tags": ["vegetarian"],
    }
    assert client.post("/api/menu", json=payload).status_code == 401
    assert client.post("/api/menu", json=payload, headers=customer_headers).status_code == 403


def test_admin_menu_crud_round_trip(client, admin_headers):
    created = client.post(
        "/api/menu",
        json={
            "name": "Test Thali",
            "description": "A full plate",
            "category": "Main Course",
            "price": 320,
            "tags": ["vegetarian"],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    patched = client.patch(
        f"/api/menu/{item_id}",
        json={"price": 350, "tags": ["vegetarian", "spicy"]},
        headers=admin_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["price"] == 350
    assert "spicy" in patched.json()["tags"]

    toggled = client.patch(f"/api/menu/{item_id}/availability", headers=admin_headers)
    assert toggled.json()["is_available"] is False

    assert client.delete(f"/api/menu/{item_id}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/menu/{item_id}").status_code == 404


def test_contradictory_tags_are_rejected(client, admin_headers):
    response = client.post(
        "/api/menu",
        json={
            "name": "Impossible Dish",
            "description": "both",
            "category": "Main Course",
            "price": 100,
            "tags": ["vegetarian", "non-vegetarian"],
        },
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_negative_price_is_rejected(client, admin_headers):
    response = client.post(
        "/api/menu",
        json={
            "name": "Free Lunch",
            "description": "no",
            "category": "Main Course",
            "price": -50,
            "tags": [],
        },
        headers=admin_headers,
    )
    assert response.status_code == 422
