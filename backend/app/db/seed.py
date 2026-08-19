"""Seed the database with demo users, a realistic menu, and sample orders.

Run:  python -m app.db.seed          (idempotent — safe to re-run)
      python -m app.db.seed --reset  (drop everything first)

The menu is deliberately varied along the axes the AI search is judged on:
price spread around the 200-rupee mark, a real veg/non-veg split, spicy and
mild dishes, and fried vs grilled/steamed preparations so that "a light
lunch that is not fried" has both correct and incorrect answers available.
"""
import argparse
import random
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import (
    MenuItem,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    User,
    UserRole,
)
from app.services.ai_search import refresh_embeddings

# name, description, category, price, tags, emoji
MENU: list[tuple[str, str, str, float, list[str], str]] = [
    # --- Starters ---------------------------------------------------------
    ("Paneer Tikka", "Cubes of cottage cheese marinated in yogurt and spices, char-grilled in the tandoor. Smoky, not oily.", "Starters", 240, ["vegetarian", "spicy"], "🧀"),
    ("Hara Bhara Kebab", "Pan-seared patties of spinach, green peas and potato with mild green cardamom. Light and shallow-cooked.", "Starters", 190, ["vegetarian"], "🥬"),
    ("Chilli Paneer Dry", "Cottage cheese tossed with green chillies, capsicum and soy in a fiery Indo-Chinese glaze. Deep-fried before tossing.", "Starters", 220, ["vegetarian", "spicy"], "🌶️"),
    ("Tandoori Chicken Half", "Bone-in chicken marinated overnight in yogurt, red chilli and garam masala, roasted in the clay oven. No frying.", "Starters", 320, ["non-vegetarian", "spicy"], "🍗"),
    ("Crispy Corn", "Sweet corn kernels deep-fried till crunchy, tossed with black pepper and curry leaf.", "Starters", 180, ["vegetarian"], "🌽"),
    ("Fish Amritsari", "River sole in a gram flour batter, deep-fried with carom seed and lemon.", "Starters", 340, ["non-vegetarian", "spicy"], "🐟"),
    ("Tomato Shorba", "Clear, slow-simmered tomato and basil broth finished with cracked pepper. Very light.", "Starters", 140, ["vegetarian", "vegan"], "🍅"),
    ("Chicken Malai Tikka", "Boneless chicken in a mild cream, cheese and white pepper marinade, grilled soft. Not spicy at all.", "Starters", 330, ["non-vegetarian"], "🍢"),
    ("Masala Papad", "Roasted lentil wafer topped with raw onion, tomato, green chilli and chaat masala. Crisp, sharp, roasted not fried.", "Starters", 90, ["vegetarian", "vegan", "spicy"], "🫓"),
    ("Chana Chaat", "Boiled black chickpeas tossed cold with onion, green chilli, lime and roasted cumin. Light, high protein, no oil.", "Starters", 150, ["vegetarian", "vegan", "spicy"], "🥗"),
    ("Veg Kolhapuri", "Mixed vegetables in the fierce dark red Kolhapuri masala of western Maharashtra. One of the hottest things on the menu.", "Main Course", 195, ["vegetarian", "vegan", "spicy"], "🔥"),

    # --- Main Course ------------------------------------------------------
    ("Dal Tadka", "Yellow lentils tempered with cumin, garlic and ghee. Everyday comfort, gently spiced.", "Main Course", 180, ["vegetarian"], "🍲"),
    ("Dal Makhani", "Black lentils simmered overnight with butter and cream. Rich and heavy.", "Main Course", 260, ["vegetarian"], "🫘"),
    ("Palak Paneer", "Cottage cheese in a smooth spinach gravy with a whisper of garlic. Mild and nourishing.", "Main Course", 270, ["vegetarian"], "🥬"),
    ("Kadai Paneer", "Cottage cheese with bell peppers in a coarse-ground coriander and red chilli masala. Properly hot.", "Main Course", 290, ["vegetarian", "spicy"], "🌶️"),
    ("Butter Chicken", "Tandoor-cooked chicken in a tomato, butter and cashew gravy. Sweet, mild, very rich.", "Main Course", 380, ["non-vegetarian", "contains-nuts"], "🍛"),
    ("Chicken Chettinad", "Chicken in a roasted peppercorn, fennel and dried red chilli masala from Tamil Nadu. Seriously spicy.", "Main Course", 360, ["non-vegetarian", "spicy"], "🔥"),
    ("Mutton Rogan Josh", "Slow-cooked lamb in a Kashmiri chilli and fennel gravy. Deep and warming.", "Main Course", 450, ["non-vegetarian", "spicy"], "🍖"),
    ("Mixed Vegetable Korma", "Seasonal vegetables in a mild coconut and cashew gravy. No chilli heat.", "Main Course", 240, ["vegetarian", "contains-nuts"], "🥕"),
    ("Bhindi Masala", "Okra sautéed dry with onion, tomato and amchur. Light on oil, no gravy.", "Main Course", 210, ["vegetarian", "vegan"], "🫑"),
    ("Chole Masala", "Chickpeas stewed with tea-leaf water, ginger and pomegranate seed powder. Tangy and hot.", "Main Course", 200, ["vegetarian", "vegan", "spicy"], "🫛"),
    ("Grilled Fish Steak", "Line-caught basa fillet grilled with lemon, olive oil and herbs. Served with steamed vegetables. Very light.", "Main Course", 390, ["non-vegetarian"], "🐟"),

    # --- Rice & Biryani ---------------------------------------------------
    ("Hyderabadi Chicken Biryani", "Long-grain basmati layered with marinated chicken and fried onion, sealed and dum-cooked. Fiery.", "Rice & Biryani", 340, ["non-vegetarian", "spicy"], "🍚"),
    ("Vegetable Dum Biryani", "Basmati layered with root vegetables, mint and saffron, sealed with dough. Medium heat.", "Rice & Biryani", 260, ["vegetarian"], "🍚"),
    ("Jeera Rice", "Steamed basmati tossed with cumin in ghee. Plain and light.", "Rice & Biryani", 150, ["vegetarian"], "🍚"),
    ("Curd Rice", "Soft rice folded with set curd, curry leaf and mustard seed. Cooling, no chilli.", "Rice & Biryani", 160, ["vegetarian"], "🥣"),
    ("Steamed Basmati Rice", "Plain long-grain basmati, steamed.", "Rice & Biryani", 120, ["vegetarian", "vegan"], "🍚"),

    # --- Breads -----------------------------------------------------------
    ("Tandoori Roti", "Whole wheat flatbread baked on the tandoor wall. No oil.", "Breads", 40, ["vegetarian", "vegan"], "🫓"),
    ("Butter Naan", "Refined flour bread baked in the tandoor and brushed with butter.", "Breads", 70, ["vegetarian"], "🫓"),
    ("Garlic Naan", "Tandoor naan studded with garlic and coriander.", "Breads", 85, ["vegetarian"], "🧄"),
    ("Lachha Paratha", "Layered whole wheat paratha, crisp outside and soft inside. Cooked with ghee.", "Breads", 80, ["vegetarian"], "🥯"),

    # --- Desserts ---------------------------------------------------------
    ("Gulab Jamun", "Two milk-solid dumplings deep-fried and soaked in cardamom syrup. Served warm.", "Desserts", 130, ["vegetarian"], "🍮"),
    ("Rasmalai", "Poached cottage cheese discs in saffron and pistachio milk. Chilled, no frying.", "Desserts", 160, ["vegetarian", "contains-nuts"], "🍥"),
    ("Fruit Cream", "Seasonal fruit folded into lightly sweetened whipped cream. Light finish.", "Desserts", 140, ["vegetarian"], "🍓"),
    ("Kesar Kheer", "Rice slow-simmered in milk with saffron and cardamom.", "Desserts", 150, ["vegetarian"], "🍚"),

    # --- Beverages --------------------------------------------------------
    ("Sweet Lassi", "Thick set curd blended with sugar and a pinch of cardamom.", "Beverages", 110, ["vegetarian"], "🥛"),
    ("Masala Chaas", "Churned buttermilk with roasted cumin, black salt and coriander. Savoury and cooling.", "Beverages", 90, ["vegetarian"], "🥤"),
    ("Fresh Lime Soda", "Lime, soda and your choice of sweet or salted.", "Beverages", 80, ["vegetarian", "vegan"], "🍋"),
    ("Masala Chai", "Assam tea brewed with ginger, cardamom and milk.", "Beverages", 60, ["vegetarian"], "☕"),
    ("Cold Coffee", "Blended coffee with milk and ice cream.", "Beverages", 140, ["vegetarian"], "🧋"),
]

USERS = [
    ("admin@savora.in", "Anaya Rao", "admin123", UserRole.ADMIN),
    ("customer@savora.in", "Biplab Kar", "customer123", UserRole.CUSTOMER),
    ("rhea@savora.in", "Rhea Menon", "customer123", UserRole.CUSTOMER),
]


def seed(reset: bool = False, with_orders: bool = True) -> None:
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # --- users --------------------------------------------------------
        for email, name, password, role in USERS:
            if db.scalar(select(User).where(User.email == email)):
                continue
            db.add(
                User(
                    email=email,
                    full_name=name,
                    hashed_password=hash_password(password),
                    role=role,
                )
            )
        db.commit()

        # --- menu ---------------------------------------------------------
        created = 0
        for name, description, category, price, tags, emoji in MENU:
            if db.scalar(select(MenuItem).where(MenuItem.name == name)):
                continue
            item = MenuItem(
                name=name,
                description=description,
                category=category,
                price=price,
                is_available=True,
                image_emoji=emoji,
            )
            item.tags = tags
            db.add(item)
            created += 1
        db.commit()
        print(f"Menu: {created} items created, {len(MENU)} total defined.")

        # --- sample orders so the dashboard is not empty on first load ----
        if with_orders and not db.scalar(select(Order.id).limit(1)):
            _seed_orders(db)

        # --- embeddings ---------------------------------------------------
        from app.services.embeddings import active_provider

        provider = active_provider()
        written = refresh_embeddings(db)
        if written:
            print(f"Embeddings: {written} vectors cached via '{provider}' provider.")
        elif provider == "none":
            print(
                "Embeddings: no provider available — search runs in lexical (BM25) mode.\n"
                "            Set EMBEDDING_PROVIDER=local in .env for offline semantic search."
            )
        else:
            print(f"Embeddings: already up to date ('{provider}' provider).")
    finally:
        db.close()


def _seed_orders(db) -> None:
    random.seed(7)
    items = list(db.scalars(select(MenuItem)))
    customers = list(db.scalars(select(User).where(User.role == UserRole.CUSTOMER)))
    if not items or not customers:
        return

    today = datetime.now().replace(minute=0, second=0, microsecond=0)
    plan = [
        (OrderStatus.PICKED_UP, 6),
        (OrderStatus.READY, 2),
        (OrderStatus.PREPARING, 2),
        (OrderStatus.CONFIRMED, 2),
        (OrderStatus.PLACED, 2),
    ]

    created = 0
    for target_status, count in plan:
        for _ in range(count):
            customer = random.choice(customers)
            chosen = random.sample(items, random.randint(2, 4))
            order = Order(
                order_code=f"SV-SEED{created:03d}",
                customer_id=customer.id,
                status=target_status,
                created_at=today - timedelta(hours=random.randint(0, 8), minutes=random.randint(0, 59)),
            )
            total = 0.0
            for item in chosen:
                quantity = random.randint(1, 2)
                order.items.append(
                    OrderItem(
                        menu_item_id=item.id,
                        item_name=item.name,
                        unit_price=item.price,
                        quantity=quantity,
                    )
                )
                total += item.price * quantity
            order.total_amount = round(total, 2)

            # Write the full transition history so the audit trail is real.
            path = [
                OrderStatus.PLACED,
                OrderStatus.CONFIRMED,
                OrderStatus.PREPARING,
                OrderStatus.READY,
                OrderStatus.PICKED_UP,
            ]
            previous = None
            for step in path:
                order.events.append(
                    OrderEvent(
                        from_status=previous.value if previous else None,
                        to_status=step.value,
                        actor_email="admin@savora.in" if previous else customer.email,
                        created_at=order.created_at,
                    )
                )
                previous = step
                if step == target_status:
                    break
            db.add(order)
            created += 1
    db.commit()
    print(f"Orders: {created} sample orders created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Savora database.")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    parser.add_argument("--no-orders", action="store_true", help="skip sample orders")
    args = parser.parse_args()
    seed(reset=args.reset, with_orders=not args.no_orders)
    print("Done. Log in as admin@savora.in / admin123")
