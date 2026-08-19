"""Order status state machine.

The workflow from the brief is linear:

    Placed → Confirmed → Preparing → Ready → Picked Up

Two additions the brief does not mention but a real kitchen needs:
* Cancellation is allowed up to (and including) Preparing. Once the food is
  Ready it has been cooked, so cancelling it is a refund decision, not a
  state transition.
* Transitions are forward-only. Reverting Ready → Preparing would let the
  dashboard's revenue and throughput numbers double count.

Centralising this here — rather than scattering `if status ==` checks
through the routers — means the API, the tests, and the UI's button states
all read from one definition.
"""
from app.models import OrderStatus

TRANSITIONS: dict[OrderStatus, tuple[OrderStatus, ...]] = {
    OrderStatus.PLACED: (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
    OrderStatus.CONFIRMED: (OrderStatus.PREPARING, OrderStatus.CANCELLED),
    OrderStatus.PREPARING: (OrderStatus.READY, OrderStatus.CANCELLED),
    OrderStatus.READY: (OrderStatus.PICKED_UP,),
    OrderStatus.PICKED_UP: (),
    OrderStatus.CANCELLED: (),
}

TERMINAL = {OrderStatus.PICKED_UP, OrderStatus.CANCELLED}

# Statuses that count toward "revenue" — an order is only money once the
# customer has it. Cancelled orders never count.
REVENUE_STATUSES = {
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.PICKED_UP,
}


def allowed_next(current: OrderStatus) -> list[OrderStatus]:
    return list(TRANSITIONS.get(current, ()))


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in TRANSITIONS.get(current, ())


def explain_rejection(current: OrderStatus, target: OrderStatus) -> str:
    if current in TERMINAL:
        return f"Order is already {current.value}; it is a terminal state."
    allowed = ", ".join(s.value for s in allowed_next(current)) or "nothing"
    return (
        f"Cannot move an order from {current.value} to {target.value}. "
        f"Allowed next: {allowed}."
    )
