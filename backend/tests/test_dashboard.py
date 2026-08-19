"""Dashboard aggregates."""
import pytest


def _menu_id(client, name: str) -> int:
    items = client.get("/api/menu").json()
    return next(i["id"] for i in items if i["name"] == name)


def test_dashboard_requires_admin(client, customer_headers):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers=customer_headers).status_code == 403


def test_empty_dashboard_is_all_zeroes_not_an_error(client, admin_headers):
    body = client.get("/api/dashboard", headers=admin_headers).json()
    assert body["revenue_today"] == 0
    assert body["popular_items"] == []
    assert body["average_order_value"] == 0
    # Every status is present with a zero count so the UI can render a
    # stable set of columns rather than a jumping layout.
    assert len(body["orders_by_status"]) == 6


def test_revenue_only_counts_confirmed_orders(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")  # 180
    order = client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": dal, "quantity": 2}]},
        headers=customer_headers,
    ).json()

    # Still only Placed — not money yet.
    before = client.get("/api/dashboard", headers=admin_headers).json()
    assert before["revenue_today"] == 0
    assert before["active_orders"] == 1

    client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Confirmed"},
        headers=admin_headers,
    )
    after = client.get("/api/dashboard", headers=admin_headers).json()
    assert after["revenue_today"] == pytest.approx(360.0)
    assert after["average_order_value"] == pytest.approx(360.0)


def test_cancelled_orders_are_excluded_from_revenue(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": dal, "quantity": 1}]},
        headers=customer_headers,
    ).json()
    client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Cancelled"},
        headers=admin_headers,
    )
    body = client.get("/api/dashboard", headers=admin_headers).json()
    assert body["revenue_today"] == 0
    assert body["active_orders"] == 0


def test_popular_items_ranks_by_units_sold(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    chole = _menu_id(client, "Chole Masala")
    order = client.post(
        "/api/orders",
        json={
            "items": [
                {"menu_item_id": dal, "quantity": 3},
                {"menu_item_id": chole, "quantity": 1},
            ]
        },
        headers=customer_headers,
    ).json()
    client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Confirmed"},
        headers=admin_headers,
    )
    body = client.get("/api/dashboard", headers=admin_headers).json()
    assert body["popular_items"][0]["name"] == "Dal Tadka"
    assert body["popular_items"][0]["units_sold"] == 3
    assert body["popular_items"][0]["revenue"] == pytest.approx(540.0)
