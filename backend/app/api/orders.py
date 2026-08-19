"""Order placement, tracking, and the admin status workflow."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models import MenuItem, Order, OrderEvent, OrderItem, OrderStatus, User, UserRole
from app.schemas import OrderCreate, OrderOut, OrderStatusUpdate
from app.services.order_state import allowed_next, can_transition, explain_rejection

router = APIRouter(prefix="/orders", tags=["orders"])


def _serialise(order: Order) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.customer_name = order.customer.full_name if order.customer else ""
    out.allowed_transitions = [s.value for s in allowed_next(order.status)]
    return out


def _new_order_code() -> str:
    # Short, human-readable, unguessable enough that a customer cannot poke
    # at other people's orders by incrementing an integer.
    return f"SV-{secrets.token_hex(3).upper()}"


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def place_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderOut:
    # Collapse duplicate lines client-side mistakes into one quantity.
    quantities: dict[int, int] = {}
    for line in payload.items:
        quantities[line.menu_item_id] = quantities.get(line.menu_item_id, 0) + line.quantity

    items = list(db.scalars(select(MenuItem).where(MenuItem.id.in_(quantities))))
    found = {i.id for i in items}
    missing = set(quantities) - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown menu items: {sorted(missing)}",
        )

    # Availability is re-checked at order time, not trusted from the cart.
    # The admin may have turned an item off while it sat in someone's cart.
    unavailable = [i.name for i in items if not i.is_available]
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No longer available: {', '.join(sorted(unavailable))}",
        )

    order = Order(
        order_code=_new_order_code(),
        customer_id=user.id,
        status=OrderStatus.PLACED,
        notes=payload.notes,
    )
    total = 0.0
    for item in items:
        quantity = quantities[item.id]
        # Price is stamped here, from the server's copy — never from the
        # client payload. This is the whole reason the cart sends ids only.
        line = OrderItem(
            menu_item_id=item.id,
            item_name=item.name,
            unit_price=item.price,
            quantity=quantity,
        )
        total += item.price * quantity
        order.items.append(line)

    order.total_amount = round(total, 2)
    order.events.append(
        OrderEvent(from_status=None, to_status=OrderStatus.PLACED.value, actor_email=user.email)
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _serialise(order)


@router.get("", response_model=list[OrderOut])
def list_orders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    active_only: bool = Query(default=False),
) -> list[OrderOut]:
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.customer))
        .order_by(Order.created_at.desc())
    )
    # A customer can only ever see their own orders; the scoping happens
    # here in the query, not in a client-side filter.
    if user.role != UserRole.ADMIN:
        stmt = stmt.where(Order.customer_id == user.id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if active_only:
        stmt = stmt.where(
            Order.status.notin_([OrderStatus.PICKED_UP, OrderStatus.CANCELLED])
        )
    return [_serialise(o) for o in db.scalars(stmt)]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrderOut:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    if user.role != UserRole.ADMIN and order.customer_id != user.id:
        # 404 rather than 403: do not confirm that someone else's order id
        # exists to a customer who is fishing.
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    out = _serialise(order)
    out.events = order.events  # type: ignore[assignment]
    return out


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> OrderOut:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")

    if payload.status == order.status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is already {order.status.value}.",
        )
    if not can_transition(order.status, payload.status):
        # 422: the request is well-formed but the transition is not legal
        # for this order's current state.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=explain_rejection(order.status, payload.status),
        )

    previous = order.status
    order.status = payload.status
    order.updated_at = datetime.now(timezone.utc)
    order.events.append(
        OrderEvent(
            from_status=previous.value,
            to_status=payload.status.value,
            actor_email=admin.email,
        )
    )
    db.commit()
    db.refresh(order)
    return _serialise(order)
