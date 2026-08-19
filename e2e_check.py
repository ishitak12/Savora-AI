"""End-to-end smoke test driven through a real browser.

Not part of the deliverable's test suite — this is the verification pass:
sign in as a customer, run an AI search, order, then sign in as the admin
and push the order through the workflow, screenshotting each view.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
SHOTS = "/home/claude/savora/shots"
errors = []


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1360, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # --- customer -----------------------------------------------------
        page.goto(BASE, wait_until="networkidle")
        page.get_by_role("button", name="Customer", exact=True).click()
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_selector(".menu-grid", timeout=10000)
        page.screenshot(path=f"{SHOTS}/01-customer-menu.png", full_page=False)

        # AI search
        page.get_by_role("button", name="something spicy and vegetarian under 200 rupees").click()
        page.wait_for_selector(".search-meta", timeout=10000)
        page.wait_for_timeout(600)
        page.screenshot(path=f"{SHOTS}/02-ai-search.png")
        mode = page.query_selector(".mode-badge").inner_text()
        results = page.query_selector_all(".menu-grid .dish")
        print(f"search mode={mode} results={len(results)}")
        assert len(results) >= 1, "AI search returned nothing"

        # add to cart + checkout
        page.query_selector_all("button:has-text('Add to cart')")[0].click()
        page.get_by_role("button", name="Clear").click()
        page.wait_for_selector(".filter-row")
        page.query_selector_all("button:has-text('Add to cart')")[1].click()
        page.wait_for_timeout(300)
        page.click(".cart-fab")
        page.wait_for_selector(".cart-panel")
        page.screenshot(path=f"{SHOTS}/03-cart.png")
        page.get_by_role("button", name="Place order").click()
        page.wait_for_selector(".order-card", timeout=10000)
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SHOTS}/04-my-orders.png")
        code = page.query_selector(".order-code").inner_text()
        print(f"placed order {code}")

        page.get_by_role("button", name="Sign out").click()
        page.wait_for_selector(".login-card")

        # --- admin --------------------------------------------------------
        page.get_by_role("button", name="Admin", exact=True).click()
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_selector(".stat-row", timeout=10000)
        page.wait_for_timeout(800)
        page.screenshot(path=f"{SHOTS}/05-admin-dashboard.png", full_page=True)

        page.click("a:has-text('Orders')")
        page.wait_for_selector(".order-card", timeout=10000)
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SHOTS}/06-admin-orders.png")

        # advance the order we just placed through every stage
        for label in ["Mark Confirmed", "Mark Preparing", "Mark Ready", "Mark Picked Up"]:
            card = page.query_selector(f".order-card:has-text('{code}')")
            if card is None:
                page.click("button:has-text('All')")
                page.wait_for_timeout(600)
                card = page.query_selector(f".order-card:has-text('{code}')")
            button = card.query_selector(f"button:has-text('{label}')")
            assert button, f"{label} not offered for {code}"
            button.click()
            page.wait_for_timeout(900)
        print(f"advanced {code} to Picked Up")

        page.click("a:has-text('Menu')")
        page.wait_for_selector("table", timeout=10000)
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SHOTS}/07-admin-menu.png")

        page.click("a:has-text('Dashboard')")
        page.wait_for_selector(".stat-row")
        page.wait_for_timeout(900)
        page.screenshot(path=f"{SHOTS}/08-dashboard-after.png", full_page=True)

        # dark mode render check
        dark = browser.new_page(
            viewport={"width": 1360, "height": 900}, color_scheme="dark"
        )
        dark.goto(BASE, wait_until="networkidle")
        dark.get_by_role("button", name="Admin", exact=True).click()
        dark.get_by_role("button", name="Sign in", exact=True).click()
        dark.wait_for_selector(".stat-row", timeout=10000)
        dark.wait_for_timeout(900)
        dark.screenshot(path=f"{SHOTS}/09-dark-dashboard.png", full_page=True)

        browser.close()

    real = [e for e in errors if "favicon" not in e.lower()]
    if real:
        print("CONSOLE ERRORS:")
        for e in real[:10]:
            print("  ", e)
        sys.exit(1)
    print("E2E OK — no console errors")


if __name__ == "__main__":
    run()
