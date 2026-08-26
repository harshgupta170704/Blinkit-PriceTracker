"""
Blinkit Price Tracker — Standalone Script

Bypasses Blinkit's DataDome WAF and location gate to scrape real-time
product prices across multiple Indian cities using the Zyte API.

Usage:
    1. Add your Zyte API key to .env
    2. Populate input_products.csv
    3. Run: python blinkit_price_tracker.py
"""

import os
import re
import time
import base64
import logging
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from config import (
    PINCODES, ZYTE_API_URL, MAX_RETRIES, RETRY_DELAY,
    JS_WAIT_TIMEOUT, INPUT_CSV, OUTPUT_DIR, SCREENSHOT_DIR,
)

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))

ZYTE_API_KEY = os.getenv("ZYTE_API_KEY")

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── URL Builder ──────────────────────────────────────────────────────────────

def build_product_url(productid: str) -> str:
    """
    Build a Blinkit product URL from a productid.
    Accepts:
      - A full URL (returned as-is)
      - A relative path like 'prn/some-slug/prid/565294'
      - A numeric prid like '565294'
    """
    if productid.startswith("http"):
        return productid
    if "/" in productid:
        return f"https://blinkit.com/{productid}"
    return f"https://blinkit.com/prn/product/prid/{productid}"


# ─── JavaScript Injection Payload ─────────────────────────────────────────────

def build_js_script(pincode: str, product_url: str) -> str:
    """
    Generate the JavaScript payload that will be injected into the Zyte
    browser to bypass Blinkit's location gate.

    The script simulates human typing with random delays, clears and retypes
    the pincode (to trigger React onChange listeners), waits for the location
    dropdown, clicks the first suggestion, and then navigates to the product.
    """
    return f"""
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function typeText(element, text, delay = 80) {{
    element.focus();
    for (const char of text) {{
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeInputValueSetter.call(element, element.value + char);
        element.dispatchEvent(new Event('input', {{ bubbles: true }}));
        element.dispatchEvent(new KeyboardEvent('keydown', {{ key: char, bubbles: true }}));
        element.dispatchEvent(new KeyboardEvent('keypress', {{ key: char, bubbles: true }}));
        element.dispatchEvent(new KeyboardEvent('keyup', {{ key: char, bubbles: true }}));
        await sleep(delay + Math.random() * 60);
    }}
}}

async function clearInput(element) {{
    element.focus();
    await sleep(300);
    element.select?.();
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputValueSetter.call(element, '');
    element.dispatchEvent(new Event('input', {{ bubbles: true }}));
    element.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Backspace', bubbles: true }}));
    await sleep(200);
}}

function waitForElement(selector, timeout = 8000) {{
    return new Promise((resolve, reject) => {{
        const existing = document.querySelector(selector);
        if (existing) return resolve(existing);
        const observer = new MutationObserver(() => {{
            const el = document.querySelector(selector);
            if (el) {{
                observer.disconnect();
                resolve(el);
            }}
        }});
        observer.observe(document.body, {{ childList: true, subtree: true }});
        setTimeout(() => {{
            observer.disconnect();
            reject(new Error(`Timeout waiting for: ${{selector}}`));
        }}, timeout);
    }});
}}

async function automateLocation() {{
    console.log('Step 1: Looking for location search input...');
    const input = await waitForElement('input[name="select-locality"]');
    console.log('Found input field');

    await sleep(600);
    input.click();
    await sleep(400);

    console.log('Step 2: Typing pincode {pincode}...');
    await typeText(input, '{pincode}');
    await sleep(1000);

    console.log('Step 3: Clearing the input...');
    await clearInput(input);
    await sleep(700);

    console.log('Step 4: Typing pincode again...');
    await typeText(input, '{pincode}');

    console.log('Step 5: Waiting for location suggestions...');
    await waitForElement('.LocationSearchList__LocationListContainer-sc-93rfr7-0');
    await sleep(800);

    console.log('Step 6: Selecting first location from list...');
    const firstLocation = document.querySelector(
        '.LocationSearchList__LocationListContainer-sc-93rfr7-0'
    );
    if (!firstLocation) throw new Error('Location list not found');
    firstLocation.click();
    console.log('Clicked first location suggestion');

    await sleep(2000);

    console.log('Step 7: Navigating to product page...');
    window.location.href = '{product_url}';
    console.log('Done!');
}}

automateLocation().catch(err => console.error('Error:', err));
"""


# ─── Zyte API Call ────────────────────────────────────────────────────────────

def fetch_page_via_zyte(product_url: str, pincode: str) -> dict | None:
    """
    Call the Zyte API to:
      1. Land on the Blinkit homepage
      2. Inject JS to type the pincode and bypass the location gate
      3. Navigate to the product page
      4. Return rendered browserHtml + screenshot

    Returns the full Zyte API JSON response, or None on failure.
    """
    js_script = build_js_script(pincode, product_url)

    payload = {
        "url": "https://blinkit.com",
        "browserHtml": True,
        "javascript": True,
        "actions": [
            {"action": "evaluate", "source": js_script},
            {"action": "waitForTimeout", "timeout": JS_WAIT_TIMEOUT},
        ],
        "screenshot": True,
    }

    try:
        response = requests.post(
            ZYTE_API_URL,
            auth=(ZYTE_API_KEY, ""),
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Zyte API request failed: {e}")
        return None


def pincode_change_succeeded(zyte_response: dict) -> bool:
    """
    Inspect the Zyte actions result to confirm pincode was changed successfully.
    Returns True only if all actions completed without error.
    """
    if not zyte_response:
        return False
    actions = zyte_response.get("actions", [])
    for action in actions:
        if action.get("status") in ("notExecuted", "error"):
            return False
        if action.get("error"):
            return False
    return True


# ─── HTML Parsing ─────────────────────────────────────────────────────────────

def clean_price(raw: str | None) -> float | None:
    """Strip ₹, commas and whitespace from a price string."""
    if raw is None:
        return None
    cleaned = raw.replace("₹", "").replace(",", "").strip().rstrip(".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def scrape_product(zyte_response: dict, productid: str, pincode: str) -> dict | None:
    """
    Parse product data from the Zyte API browserHtml response.

    HTML targets (Blinkit's Tailwind CSS classes):
      Title:          <div class="tw-line-clamp-50">
      Selling Price:  <div class="tw-text-400 tw-font-bold">
      MRP:            <span class="tw-line-through">
    """
    html = zyte_response.get("browserHtml", "")
    scraped_url = zyte_response.get("url", build_product_url(productid))

    soup = BeautifulSoup(html, "lxml")

    # ── Title ─────────────────────────────────────────────────────────────
    title = None
    title_el = soup.select_one("div.tw-line-clamp-50")
    if title_el:
        title = title_el.get_text(strip=True)

    # ── Selling Price ─────────────────────────────────────────────────────
    selling_price_raw = None
    selling_price_el = soup.select_one("div.tw-text-400.tw-font-bold")
    if selling_price_el:
        selling_price_raw = selling_price_el.get_text(strip=True)
    selling_price = clean_price(selling_price_raw)

    # ── MRP ───────────────────────────────────────────────────────────────
    mrp_raw = None
    mrp_el = soup.select_one("span.tw-line-through")
    if mrp_el:
        mrp_raw = mrp_el.get_text(strip=True)
    mrp = clean_price(mrp_raw)

    # ── Discount ──────────────────────────────────────────────────────────
    discount_pct = None
    if mrp and selling_price and mrp > selling_price:
        discount_pct = round((1 - selling_price / mrp) * 100, 1)

    # ── Out of Stock Detection ────────────────────────────────────────────
    page_text = soup.get_text(separator=" ").lower()
    out_of_stock = "out of stock" in page_text or "currently unavailable" in page_text

    return {
        "productid": productid,
        "title": title,
        "selling_price": selling_price,
        "mrp": mrp,
        "discount_pct": discount_pct,
        "out_of_stock": out_of_stock,
        "pincode": pincode,
        "url": scraped_url,
        "scraped_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─── Screenshot Saver ─────────────────────────────────────────────────────────

def save_screenshot(zyte_response: dict, productid: str, pincode: str) -> str | None:
    """Decode the base64 screenshot from Zyte and save locally."""
    screenshot_b64 = zyte_response.get("screenshot")
    if not screenshot_b64:
        return None
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        screenshot_bytes = base64.b64decode(screenshot_b64)
        safe_id = re.sub(r'[^\w\-]', '_', productid)
        filename = f"{safe_id}_{pincode}_{datetime.now(IST).strftime('%Y%m%d%H%M%S')}.png"
        filepath = os.path.join(SCREENSHOT_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(screenshot_bytes)
        logger.info(f"Screenshot saved: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Screenshot save failed for {productid}: {e}")
        return None


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def load_products(csv_path: str = INPUT_CSV) -> pd.DataFrame:
    """Load product list from local CSV file."""
    if not os.path.exists(csv_path):
        logger.error(f"Input file not found: {csv_path}")
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    logger.info(f"Loaded {len(df)} products from {csv_path}")
    return df


def run_tracker():
    """
    Main entry point.
    Loads products from CSV, scrapes Blinkit prices via Zyte across
    multiple pincodes, and generates an Excel report.
    """
    if not ZYTE_API_KEY:
        logger.error("ZYTE_API_KEY not set. Copy .env.example to .env and add your key.")
        return

    products_df = load_products()
    if products_df.empty:
        return

    all_results = []
    failed_count = 0

    for pincode_info in PINCODES:
        pincode = pincode_info["pincode"]
        city = pincode_info["city"]
        logger.info(f"── Processing {city} (pincode: {pincode}) ──")

        for _, product_row in products_df.iterrows():
            productid = str(product_row["productid"])
            product_url = build_product_url(productid)
            scraped = False

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logger.info(
                        f"Scraping {productid} | {city} (attempt {attempt}/{MAX_RETRIES})"
                    )

                    zyte_response = fetch_page_via_zyte(product_url, pincode)

                    if not zyte_response:
                        raise ValueError("Zyte returned no response")

                    if not pincode_change_succeeded(zyte_response):
                        logger.warning(
                            f"Pincode change may have failed for {productid} | "
                            f"{city} — proceeding with available HTML"
                        )

                    result = scrape_product(zyte_response, productid, pincode)

                    if not result or not result.get("title"):
                        raise ValueError(
                            "Title not found — likely an error or unavailable page"
                        )

                    # Add metadata from CSV
                    result["city"] = city
                    result["brand"] = product_row.get("brand", "")
                    result["category"] = product_row.get("category", "")
                    result["sku_description"] = product_row.get("sku_description", "")

                    # Save screenshot locally
                    screenshot_path = save_screenshot(zyte_response, productid, pincode)
                    result["screenshot_path"] = screenshot_path

                    all_results.append(result)
                    logger.info(f"✅ {productid} | {city} scraped successfully")
                    scraped = True
                    break

                except Exception as e:
                    logger.warning(
                        f"Attempt {attempt}/{MAX_RETRIES} failed for {productid}: {e}"
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)

            if not scraped:
                logger.error(
                    f"❌ Skipping {productid} | {city} after {MAX_RETRIES} failed attempts"
                )
                failed_count += 1

    # ── Build DataFrame and Save ──────────────────────────────────────────
    if not all_results:
        logger.warning("No results scraped. Exiting.")
        return

    df = pd.DataFrame(all_results)
    logger.info(f"Total rows scraped: {len(df)} | Failed: {failed_count}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"blinkit_prices_{timestamp}.xlsx")
    df.to_excel(output_file, index=False)
    logger.info(f"📊 Excel report saved to: {output_file}")
    logger.info(f"✅ Done! Processed {len(df)} records across {len(PINCODES)} cities.")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_tracker()
