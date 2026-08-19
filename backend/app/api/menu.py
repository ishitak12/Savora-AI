"""Menu catalogue: public reads, admin-only writes."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import MenuItem, User
from app.schemas import MenuItemCreate, MenuItemOut, MenuItemUpdate
from app.services.ai_search import refresh_embeddings

router = APIRouter(prefix="/menu", tags=["menu"])


def _get_or_404(db: Session, item_id: int) -> MenuItem:
    item = db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Menu item {item_id} does not exist.",
        )
    return item


@router.get("", response_model=list[MenuItemOut])
def list_menu(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None),
    available_only: bool = Query(
        default=True,
        description="Customers see available items; the admin view sets this false.",
    ),
    q: str | None = Query(default=None, description="Plain substring filter"),
) -> list[MenuItem]:
    stmt = select(MenuItem)
    if available_only:
        stmt = stmt.where(MenuItem.is_available.is_(True))
    if category:
        stmt = stmt.where(MenuItem.category == category)
    if q:
        stmt = stmt.where(MenuItem.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt.order_by(MenuItem.category, MenuItem.name)))


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db)) -> list[str]:
    rows = db.execute(
        select(MenuItem.category).where(MenuItem.is_available.is_(True)).distinct()
    ).scalars()
    return sorted(rows)


@router.get("/{item_id}", response_model=MenuItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)) -> MenuItem:
    return _get_or_404(db, item_id)


@router.post(
    "", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED
)
def create_item(
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> MenuItem:
    item = MenuItem(
        name=payload.name,
        description=payload.description,
        category=payload.category,
        price=payload.price,
        is_available=payload.is_available,
        image_emoji=payload.image_emoji,
    )
    item.tags = [t.value for t in payload.tags]
    db.add(item)
    db.commit()
    db.refresh(item)
    # Embed on write so the read path never pays for it. Failure here is
    # non-fatal: search degrades to lexical for this item until it succeeds.
    refresh_embeddings(db, [item])
    return item


@router.patch("/{item_id}", response_model=MenuItemOut)
def update_item(
    item_id: int,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> MenuItem:
    item = _get_or_404(db, item_id)
    data = payload.model_dump(exclude_unset=True)
    tags = data.pop("tags", None)
    for field, value in data.items():
        setattr(item, field, value)
    if tags is not None:
        item.tags = [t.value if hasattr(t, "value") else str(t) for t in tags]
    db.commit()
    db.refresh(item)
    refresh_embeddings(db, [item])
    return item


@router.patch("/{item_id}/availability", response_model=MenuItemOut)
def toggle_availability(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> MenuItem:
    item = _get_or_404(db, item_id)
    item.is_available = not item.is_available
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    item = _get_or_404(db, item_id)
    # Hard delete would orphan historical order lines' foreign key. Order
    # items keep a name/price snapshot, so the receipt survives, but we
    # still guard the FK by checking for references first.
    from app.models import OrderItem  # local import avoids a cycle at module load

    referenced = db.scalar(
        select(OrderItem.id).where(OrderItem.menu_item_id == item_id).limit(1)
    )
    if referenced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This item appears on existing orders and cannot be deleted. "
                "Mark it unavailable instead to remove it from the menu."
            ),
        )
    db.delete(item)
    db.commit()
