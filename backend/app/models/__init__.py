"""Domain model.

Four tables:
  users        - admin and customer accounts
  menu_items   - the catalogue, plus a cached embedding vector
  orders       - one row per placed order, carries the workflow status
  order_items  - line items, price-stamped at order time

Design note on order_items: unit_price and item_name are copied onto the
line item rather than joined from menu_items at read time. An order is a
financial record; if the admin later reprices Paneer Tikka, yesterday's
receipts must not change. This is deliberate denormalisation.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CUSTOMER = "customer"


class DietaryTag(str, enum.Enum):
    VEGETARIAN = "vegetarian"
    NON_VEGETARIAN = "non-vegetarian"
    SPICY = "spicy"
    VEGAN = "vegan"
    CONTAINS_NUTS = "contains-nuts"


class OrderStatus(str, enum.Enum):
    PLACED = "Placed"
    CONFIRMED = "Confirmed"
    PREPARING = "Preparing"
    READY = "Ready"
    PICKED_UP = "Picked Up"
    CANCELLED = "Cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda e: [m.value for m in e]),
        default=UserRole.CUSTOMER,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), index=True)
    price: Mapped[float] = mapped_column(Float)
    # Tags are stored as a comma-separated string. SQLite has no array type
    # and the cardinality here is tiny; a join table would be ceremony.
    tags_raw: Mapped[str] = mapped_column(String(255), default="")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    image_emoji: Mapped[str] = mapped_column(String(16), default="🍽️")

    # Cached embedding of the searchable text, refreshed whenever the item's
    # text changes. Stored as JSON so we never re-pay the embedding API cost
    # on a read path.
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    @property
    def tags(self) -> list[str]:
        return [t for t in (self.tags_raw or "").split(",") if t]

    @tags.setter
    def tags(self, values: list[str]) -> None:
        self.tags_raw = ",".join(sorted({v.strip() for v in values if v.strip()}))

    @property
    def search_text(self) -> str:
        """The text the AI layer indexes. Kept in one place so the embedding
        fingerprint and the lexical index can never drift apart."""
        return (
            f"{self.name}. {self.description} "
            f"Category: {self.category}. "
            f"Tags: {', '.join(self.tags)}. "
            f"Price: {self.price:.0f} rupees."
        )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, values_callable=lambda e: [m.value for m in e]),
        default=OrderStatus.PLACED,
        index=True,
    )
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    customer: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderEvent.created_at",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (UniqueConstraint("order_id", "menu_item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("menu_items.id"), index=True
    )
    item_name: Mapped[str] = mapped_column(String(150))  # price/name snapshot
    unit_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    order: Mapped["Order"] = relationship(back_populates="items")

    @property
    def line_total(self) -> float:
        return round(self.unit_price * self.quantity, 2)


class OrderEvent(Base):
    """Append-only audit trail of status transitions.

    Keeps the order table's `status` column authoritative for reads while
    preserving how it got there — useful for the dashboard and for answering
    "when was this order confirmed?".
    """

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    order: Mapped["Order"] = relationship(back_populates="events")
