"""Admin dashboard aggregates.

All figures are computed in SQL rather than by loading orders into Python,
so the endpoint stays flat as order volume grows. The dashboard uses a
rolling 24-hour window so seeded demo orders and live orders both show up
without depending on midnight boundaries.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Order, OrderItem, OrderStatus, User
from app.schemas import (
    DashboardOut,
    PopularItem,
    RevenuePoint,
    StatusCount,
)
from app.services.order_state import REVENUE_STATUSES

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _day_bounds() -> tuple[datetime, datetime]:
    end = datetime.now()
    start = end - timedelta(hours=24)
    return start, end


@router.get("", response_model=DashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DashboardOut:
    start, end = _day_bounds()
    revenue_statuses = [s for s in REVENUE_STATUSES]

    # --- orders grouped by status (all time, for the kanban counts) ------
    status_rows = db.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    ).all()
    counts = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in status_rows}
    orders_by_status = [
        StatusCount(status=s.value, count=counts.get(s.value, 0))
        for s in OrderStatus
    ]

    # --- rolling revenue -------------------------------------------------
    revenue_today = db.scalar(
        select(func.coalesce(func.sum(Order.total_amount), 0.0)).where(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.in_(revenue_statuses),
        )
    ) or 0.0

    orders_today = db.scalar(
        select(func.count(Order.id)).where(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status != OrderStatus.CANCELLED,
        )
    ) or 0

    # --- popular items (rolling 24h, by units sold) ----------------------
    popular_rows = db.execute(
        select(
            OrderItem.menu_item_id,
            OrderItem.item_name,
            func.sum(OrderItem.quantity).label("units"),
            func.sum(cast(OrderItem.quantity, Float) * OrderItem.unit_price).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.in_(revenue_statuses),
        )
        .group_by(OrderItem.menu_item_id, OrderItem.item_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(6)
    ).all()

    popular_items = [
        PopularItem(
            menu_item_id=row[0],
            name=row[1],
            units_sold=int(row[2] or 0),
            revenue=round(float(row[3] or 0.0), 2),
        )
        for row in popular_rows
    ]

    # --- revenue by hour -------------------------------------------------
    hour_rows = db.execute(
        select(
            func.strftime("%Y-%m-%d %H:00", Order.created_at).label("hour"),
            func.coalesce(func.sum(Order.total_amount), 0.0),
            func.count(Order.id),
        )
        .where(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.in_(revenue_statuses),
        )
        .group_by("hour")
        .order_by("hour")
    ).all()
    hour_lookup = {row[0]: (row[1], row[2]) for row in hour_rows}
    hour_buckets = []
    bucket_start = start.replace(minute=0, second=0, microsecond=0)
    for index in range(24):
        bucket = bucket_start + timedelta(hours=index)
        key = bucket.strftime("%Y-%m-%d %H:00")
        amount, count = hour_lookup.get(key, (0.0, 0))
        hour_buckets.append(
            RevenuePoint(
                hour=bucket.strftime("%H:00"),
                revenue=round(float(amount or 0.0), 2),
                orders=int(count or 0),
            )
        )
    revenue_by_hour = hour_buckets

    active_orders = db.scalar(
        select(func.count(Order.id)).where(
            Order.status.notin_([OrderStatus.PICKED_UP, OrderStatus.CANCELLED])
        )
    ) or 0

    paid_today = db.scalar(
        select(func.count(Order.id)).where(
            Order.created_at >= start,
            Order.created_at < end,
            Order.status.in_(revenue_statuses),
        )
    ) or 0

    return DashboardOut(
        orders_by_status=orders_by_status,
        popular_items=popular_items,
        revenue_today=round(float(revenue_today), 2),
        orders_today=int(orders_today),
        average_order_value=round(float(revenue_today) / paid_today, 2) if paid_today else 0.0,
        revenue_by_hour=revenue_by_hour,
        active_orders=int(active_orders),
    )
