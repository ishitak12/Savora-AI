"""Order placement, isolation between customers, and the status machine."""
import pytest

from app.models import OrderStatus
from app.services.order_state import allowed_next, can_transition


def _menu_id(client, name: str) -> int:
    items = client.get("/api/menu", params={"available_only": False}).json()
    return next(i["id"] for i in items if i["name"] == name)


def _place(client, headers, lines) -> dict:
    response = client.post("/api/orders", json={"items": lines, "notes": ""}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_place_order_totals_from_server_prices(client, customer_headers):
    dal = _menu_id(client, "Dal Tadka")       # 180
    chole = _menu_id(client, "Chole Masala")  # 200
    order = _place(
        client,
        customer_headers,
        [{"menu_item_id": dal, "quantity": 2}, {"menu_item_id": chole, "quantity": 1}],
    )
    assert order["total_amount"] == pytest.approx(560.0)
    assert order["status"] == "Placed"
    assert order["order_code"].startswith("SV-")


def test_duplicate_cart_lines_are_merged(client, customer_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(
        client,
        customer_headers,
        [{"menu_item_id": dal, "quantity": 1}, {"menu_item_id": dal, "quantity": 2}],
    )
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 3
    assert order["total_amount"] == pytest.approx(540.0)


def test_ordering_an_unavailable_item_conflicts(client, customer_headers):
    sold_out = _menu_id(client, "Sold Out Special")
    response = client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": sold_out, "quantity": 1}]},
        headers=customer_headers,
    )
    assert response.status_code == 409
    assert "no longer available" in response.json()["detail"].lower()


def test_ordering_unknown_item_404s(client, customer_headers):
    response = client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": 9999, "quantity": 1}]},
        headers=customer_headers,
    )
    assert response.status_code == 404


def test_empty_cart_is_rejected(client, customer_headers):
    response = client.post("/api/orders", json={"items": []}, headers=customer_headers)
    assert response.status_code == 422


def test_ordering_requires_authentication(client):
    assert client.post("/api/orders", json={"items": [{"menu_item_id": 1, "quantity": 1}]}).status_code == 401


def test_customer_cannot_see_another_customers_order(
    client, customer_headers, other_customer_headers
):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])

    assert client.get(f"/api/orders/{order['id']}", headers=other_customer_headers).status_code == 404
    assert client.get(f"/api/orders/{order['id']}", headers=customer_headers).status_code == 200

    visible = client.get("/api/orders", headers=other_customer_headers).json()
    assert all(o["id"] != order["id"] for o in visible)


def test_admin_sees_all_orders(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    visible = client.get("/api/orders", headers=admin_headers).json()
    assert any(o["id"] == order["id"] for o in visible)


def test_full_happy_path_workflow(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])

    for target in ["Confirmed", "Preparing", "Ready", "Picked Up"]:
        response = client.patch(
            f"/api/orders/{order['id']}/status",
            json={"status": target},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target

    final = client.get(f"/api/orders/{order['id']}", headers=admin_headers).json()
    assert final["allowed_transitions"] == []
    # Placed + four transitions = five audit events.
    assert len(final["events"]) == 5


def test_illegal_skip_forward_is_rejected(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    response = client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Ready"},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert "Cannot move an order from Placed to Ready" in response.json()["detail"]


def test_backwards_transition_is_rejected(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    client.patch(f"/api/orders/{order['id']}/status", json={"status": "Confirmed"}, headers=admin_headers)
    response = client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Placed"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_customer_cannot_change_status(client, customer_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    response = client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Confirmed"},
        headers=customer_headers,
    )
    assert response.status_code == 403


def test_cannot_cancel_after_ready(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    for target in ["Confirmed", "Preparing", "Ready"]:
        client.patch(f"/api/orders/{order['id']}/status", json={"status": target}, headers=admin_headers)
    response = client.patch(
        f"/api/orders/{order['id']}/status",
        json={"status": "Cancelled"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_deleting_an_ordered_item_conflicts(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    response = client.delete(f"/api/menu/{dal}", headers=admin_headers)
    assert response.status_code == 409


def test_order_price_snapshot_survives_a_reprice(client, customer_headers, admin_headers):
    dal = _menu_id(client, "Dal Tadka")
    order = _place(client, customer_headers, [{"menu_item_id": dal, "quantity": 1}])
    client.patch(f"/api/menu/{dal}", json={"price": 999}, headers=admin_headers)
    refetched = client.get(f"/api/orders/{order['id']}", headers=customer_headers).json()
    assert refetched["items"][0]["unit_price"] == pytest.approx(180.0)
    assert refetched["total_amount"] == pytest.approx(180.0)


def test_state_machine_definition_is_linear_and_terminal():
    assert can_transition(OrderStatus.PLACED, OrderStatus.CONFIRMED)
    assert not can_transition(OrderStatus.PLACED, OrderStatus.PREPARING)
    assert allowed_next(OrderStatus.PICKED_UP) == []
    assert allowed_next(OrderStatus.CANCELLED) == []
