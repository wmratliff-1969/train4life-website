"""
EasyList → Facebook Marketplace Auto-Poster
============================================
Run on your Windows PC.  Requires:
  pip install selenium requests Pillow

Chrome + ChromeDriver must be installed and on PATH.
You must already be logged into Facebook in the Chrome profile
(set CHROME_PROFILE_PATH below or it will use the default profile).

Usage:
  python post_to_facebook.py              # runs once then exits
  python post_to_facebook.py --loop 60    # polls every 60 seconds

Flow per listing:
  1. GET /api/easylist/pending  → list of pending listings
  2. Open Facebook Marketplace → Create new listing
  3. Fill in: photos, title, price, category, condition, description
  4. Submit the listing
  5. POST /api/easylist/mark-posted  → remove from queue
"""

import argparse
import base64
import io
import os
import sys
import tempfile
import time
import json

import requests
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ── Config ────────────────────────────────────────────────────────────────────

SERVER_URL   = "https://magnificent-curiosity-production-1744.up.railway.app"
APP_KEY      = "Smallville2006"
HEADERS      = {"X-App-Key": APP_KEY, "Content-Type": "application/json"}

# Path to your Chrome profile directory (so you stay logged in to Facebook).
# Windows example: C:\Users\YourName\AppData\Local\Google\Chrome\User Data
# Leave as None to use a fresh profile each run (you'll need to log in manually).
CHROME_PROFILE_PATH = None   # e.g. r"C:\Users\Mark\AppData\Local\Google\Chrome\User Data"
CHROME_PROFILE_NAME = "Default"

# How many seconds to wait for page elements before giving up
WAIT_TIMEOUT = 20

FB_MARKETPLACE_CREATE = "https://www.facebook.com/marketplace/create/item"

# Map EasyList category names → Facebook Marketplace category selections
# Adjust as needed based on what you see in the Facebook UI
CATEGORY_MAP = {
    "Furniture":    "Home & Garden",
    "Electronics":  "Electronics",
    "Clothing":     "Clothing & Accessories",
    "Home Goods":   "Home & Garden",
    "Toys":         "Toys & Games",
    "Sports":       "Sporting Goods",
    "Other":        "Miscellaneous",
}

# Map EasyList condition → Facebook Marketplace condition label
CONDITION_MAP = {
    "Like New": "Like new",
    "Good":     "Good",
    "Fair":     "Fair",
    "Poor":     "Poor",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_pending():
    """Fetch pending listings from the server."""
    try:
        r = requests.get(f"{SERVER_URL}/api/easylist/pending", headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("listings", [])
    except Exception as e:
        print(f"[ERROR] Could not fetch pending listings: {e}")
        return []


def mark_posted(listing_id):
    """Tell the server this listing has been posted (removes from pending queue)."""
    try:
        r = requests.post(
            f"{SERVER_URL}/api/easylist/mark-posted",
            headers=HEADERS,
            json={"id": listing_id},
            timeout=15,
        )
        r.raise_for_status()
        result = r.json()
        if result.get("ok"):
            print(f"  [✓] Marked as posted: {listing_id}")
        else:
            print(f"  [!] Server said not found: {listing_id}")
    except Exception as e:
        print(f"  [ERROR] Could not mark posted: {e}")


def mark_sold(listing_id):
    """Tell the server this listing has been sold (status → sold)."""
    try:
        r = requests.post(
            f"{SERVER_URL}/api/easylist/mark-sold",
            headers=HEADERS,
            json={"id": listing_id},
            timeout=15,
        )
        r.raise_for_status()
        result = r.json()
        if result.get("ok"):
            print(f"  [✓] Marked as sold: {listing_id}")
        else:
            print(f"  [!] mark-sold: server said not found: {listing_id}")
    except Exception as e:
        print(f"  [ERROR] Could not mark sold: {e}")


def b64_to_tempfile(b64_str, idx=0):
    """Decode a base64 image string to a temporary PNG file, return its path."""
    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw))
    tmp = tempfile.NamedTemporaryFile(
        suffix=f"_listing_{idx}.png", delete=False, prefix="easylist_"
    )
    img.save(tmp.name, "PNG")
    tmp.close()
    return tmp.name


def build_driver():
    """Create a Chrome WebDriver with optional profile."""
    opts = Options()
    if CHROME_PROFILE_PATH:
        opts.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
        opts.add_argument(f"--profile-directory={CHROME_PROFILE_NAME}")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    # Uncomment to run headless (no browser window):
    # opts.add_argument("--headless=new")
    return webdriver.Chrome(options=opts)


def wait_for(driver, by, selector, timeout=WAIT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def click_text(driver, text, timeout=WAIT_TIMEOUT):
    """Click an element that contains exactly this visible text."""
    el = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, f"//*[normalize-space(text())='{text}']"))
    )
    el.click()
    return el


def type_into(driver, by, selector, text, clear=True, timeout=WAIT_TIMEOUT):
    el = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )
    if clear:
        el.clear()
    el.send_keys(text)
    return el

# ── Core posting logic ────────────────────────────────────────────────────────

def post_listing(driver, listing):
    """Navigate to Marketplace create page and fill in all fields."""
    title     = listing.get("title", "Item for Sale")
    price     = listing.get("price", "0").replace("$", "").strip()
    condition = listing.get("condition", "Good")
    category  = listing.get("category", "Other")
    desc      = listing.get("description", "")
    photos_b64 = listing.get("photos", [])  # list of base64 strings

    fb_condition = CONDITION_MAP.get(condition, "Good")
    fb_category  = CATEGORY_MAP.get(category, "Miscellaneous")

    print(f"  → Navigating to Marketplace create page…")
    driver.get(FB_MARKETPLACE_CREATE)
    time.sleep(3)

    # ── Upload photos ──────────────────────────────────────────────────────
    temp_files = []
    if photos_b64:
        print(f"  → Uploading {len(photos_b64)} photo(s)…")
        for i, b64 in enumerate(photos_b64[:10]):   # Facebook max 10 photos
            tmp_path = b64_to_tempfile(b64, i)
            temp_files.append(tmp_path)

        try:
            file_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys("\n".join(temp_files))
            time.sleep(2)
        except TimeoutException:
            print("  [!] Could not find file upload input — skipping photos")

    # ── Title ──────────────────────────────────────────────────────────────
    print(f"  → Filling title: {title}")
    try:
        title_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//label[contains(., 'Title')]//following-sibling::div//input | //input[@aria-label='Title']")
            )
        )
        title_input.clear()
        title_input.send_keys(title)
        time.sleep(0.5)
    except TimeoutException:
        print("  [!] Title field not found")

    # ── Price ──────────────────────────────────────────────────────────────
    print(f"  → Filling price: ${price}")
    try:
        price_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@aria-label='Price'] | //label[contains(., 'Price')]//following-sibling::div//input")
            )
        )
        price_input.clear()
        price_input.send_keys(price)
        time.sleep(0.5)
    except TimeoutException:
        print("  [!] Price field not found")

    # ── Category ──────────────────────────────────────────────────────────
    print(f"  → Setting category: {fb_category}")
    try:
        cat_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@aria-label='Category'] | //label[contains(.,'Category')]//following-sibling::div//input")
            )
        )
        cat_input.clear()
        cat_input.send_keys(fb_category)
        time.sleep(1)
        # Click first matching option in the dropdown
        option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//li[contains(.,'{fb_category}')] | //div[@role='option'][contains(.,'{fb_category}')]")
            )
        )
        option.click()
        time.sleep(0.5)
    except TimeoutException:
        print(f"  [!] Category dropdown option not found for: {fb_category}")

    # ── Condition ──────────────────────────────────────────────────────────
    print(f"  → Setting condition: {fb_condition}")
    try:
        cond_select = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//label[contains(.,'Condition')]//following-sibling::div | //*[@aria-label='Condition']")
            )
        )
        cond_select.click()
        time.sleep(0.5)
        cond_option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//span[normalize-space(text())='{fb_condition}'] | //div[@role='option'][contains(.,'{fb_condition}')]")
            )
        )
        cond_option.click()
        time.sleep(0.5)
    except TimeoutException:
        print(f"  [!] Condition option not found for: {fb_condition}")

    # ── Description ───────────────────────────────────────────────────────
    if desc:
        print(f"  → Filling description…")
        try:
            desc_input = WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//textarea[@aria-label='Description'] | //label[contains(.,'Description')]//following-sibling::div//textarea | //div[@aria-label='Description']")
                )
            )
            desc_input.clear()
            desc_input.send_keys(desc)
            time.sleep(0.5)
        except TimeoutException:
            print("  [!] Description field not found")

    # No Trades checkbox (if visible)
    if listing.get("noTrades"):
        try:
            no_trade = driver.find_element(
                By.XPATH, "//span[contains(text(),'No trades')]//ancestor::label"
            )
            no_trade.click()
            time.sleep(0.3)
        except NoSuchElementException:
            pass

    # ── Next / Publish ─────────────────────────────────────────────────────
    print(f"  → Clicking Next…")
    try:
        next_btn = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[@aria-label='Next'] | //span[normalize-space(text())='Next']//ancestor::div[@role='button']")
            )
        )
        next_btn.click()
        time.sleep(3)
    except TimeoutException:
        print("  [!] Next button not found — trying Publish directly")

    print(f"  → Clicking Publish…")
    try:
        publish_btn = WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[@aria-label='Publish'] | //span[normalize-space(text())='Publish']//ancestor::div[@role='button']")
            )
        )
        publish_btn.click()
        time.sleep(4)
        print(f"  [✓] Published!")
    except TimeoutException:
        print("  [!] Publish button not found — listing may not have been submitted")
        # Cleanup temps and return False to skip mark-posted
        for f in temp_files:
            try: os.unlink(f)
            except: pass
        return False

    # ── Cleanup temp files ─────────────────────────────────────────────────
    for f in temp_files:
        try: os.unlink(f)
        except: pass

    return True

# ── Main loop ─────────────────────────────────────────────────────────────────

def run_once(driver):
    listings = get_pending()
    if not listings:
        print("[i] No pending listings.")
        return

    print(f"[i] Found {len(listings)} pending listing(s).")
    for listing in listings:
        lid   = listing.get("id", "?")
        title = listing.get("title", "?")
        print(f"\n[>] Posting: {title} (id={lid})")
        try:
            success = post_listing(driver, listing)
            if success:
                mark_posted(lid)   # remove from pending queue
                mark_sold(lid)     # update status → sold on server
            else:
                print(f"  [!] Skipping mark-posted/sold due to posting failure")
        except Exception as e:
            print(f"  [ERROR] Unexpected error posting {lid}: {e}")
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="EasyList → Facebook Marketplace auto-poster")
    parser.add_argument("--loop", type=int, default=0,
                        help="Poll interval in seconds (0 = run once and exit)")
    args = parser.parse_args()

    print("=== EasyList Facebook Marketplace Auto-Poster ===")
    print(f"Server: {SERVER_URL}")
    driver = build_driver()

    try:
        if args.loop > 0:
            print(f"Polling every {args.loop} seconds. Ctrl+C to stop.\n")
            while True:
                run_once(driver)
                print(f"\n[i] Sleeping {args.loop}s…")
                time.sleep(args.loop)
        else:
            run_once(driver)
    except KeyboardInterrupt:
        print("\n[i] Stopped.")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
