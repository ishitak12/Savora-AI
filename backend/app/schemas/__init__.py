"""Pydantic request/response contracts.

Kept separate from the ORM models so the wire format can evolve without
leaking database columns (e.g. we never serialise `embedding_json`).
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import DietaryTag, OrderStatus, UserRole


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.CUSTOMER


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------
class MenuItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=1000)
    category: str = Field(min_length=1, max_length=80)
    price: float = Field(gt=0, le=100_000)
    tags: list[DietaryTag] = Field(default_factory=list)
    is_available: bool = True
    image_emoji: str = "🍽️"

    @field_validator("tags")
    @classmethod
    def _reject_contradictory_tags(cls, v: list[DietaryTag]) -> list[DietaryTag]:
        if DietaryTag.VEGETARIAN in v and DietaryTag.NON_VEGETARIAN in v:
            raise ValueError("an item cannot be both vegetarian and non-vegetarian")
        return v


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemUpdate(BaseModel):
    """All fields optional — this backs PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    price: float | None = Field(default=None, gt=0, le=100_000)
    tags: list[DietaryTag] | None = None
    is_available: bool | None = None
    image_emoji: str | None = None


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    category: str
    price: float
    tags: list[str]
    is_available: bool
    image_emoji: str


# --------------------------------------------------------------------------
# AI search
# --------------------------------------------------------------------------
class ParsedConstraints(BaseModel):
    max_price: float | None = None
    min_price: float | None = None
    require_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    source: str = "rules"  # "rules" | "llm" | "rules+llm"


class SearchResult(BaseModel):
    item: MenuItemOut
    score: float = Field(description="0-1 relevance, higher is better")
    reason: str = ""


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    constraints: ParsedConstraints
    search_mode: str = Field(
        description=(
            "Which path actually served this request: "
            "'semantic+rerank', 'semantic', 'lexical+rerank', or 'lexical'"
        )
    )
    degraded: bool = False
    notes: list[str] = Field(default_factory=list)
    took_ms: int = 0


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=8, ge=1, le=25)


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------
class CartLine(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=50)


class OrderCreate(BaseModel):
    items: list[CartLine] = Field(min_length=1)
    notes: str = Field(default="", max_length=500)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    menu_item_id: int
    item_name: str
    unit_price: float
    quantity: int
    line_total: float


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor_email: str
    created_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_code: str
    status: OrderStatus
    total_amount: float
    notes: str
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]
    customer_name: str = ""
    allowed_transitions: list[str] = Field(default_factory=list)
    events: list[OrderEventOut] = Field(default_factory=list)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
class StatusCount(BaseModel):
    status: str
    count: int


class PopularItem(BaseModel):
    menu_item_id: int
    name: str
    units_sold: int
    revenue: float


class RevenuePoint(BaseModel):
    hour: str
    revenue: float
    orders: int


class DashboardOut(BaseModel):
    orders_by_status: list[StatusCount]
    popular_items: list[PopularItem]
    revenue_today: float
    orders_today: int
    average_order_value: float
    revenue_by_hour: list[RevenuePoint]
    active_orders: int
