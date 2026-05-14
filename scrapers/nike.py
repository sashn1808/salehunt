import requests
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nike.com/",
    "nike-api-caller-id": "com.nike.commerce.nikedotcom.web",
}

API_BASE = "https://api.nike.com"

SALE_CATEGORIES = [
    ("https://www.nike.com/w/mens-sale-3yaepznik1",   "Men"),
    ("https://www.nike.com/w/womens-sale-3yaepz5e1x", "Women"),
]


def _parse_gender(subtitle, fallback_gender="Unisex"):
    s = (subtitle or "").lower()
    if "women" in s:
        return "Women"
    if "men" in s:
        return "Men"
    if any(k in s for k in ["kid", "boys", "girls", "baby", "toddler", "infant"]):
        return "Kids"
    return fallback_gender


def _parse_groupings(groupings, fallback_gender="Unisex"):
    products = []
    for group in groupings:
        for p in group.get("products", []):
            try:
                prices = p.get("prices", {})
                current = prices.get("currentPrice")
                initial = prices.get("initialPrice")
                if not current or not initial or float(current) >= float(initial):
                    continue
                discount = prices.get("discountPercentage") or round((1 - float(current) / float(initial)) * 100)
                copy = p.get("copy", {})
                title = copy.get("title", "")
                subtitle = copy.get("subTitle", "")
                name = f"{title} {subtitle}".strip()
                images = p.get("colorwayImages", {})
                image = images.get("portraitURL") or images.get("squarishURL") or ""
                pdp = p.get("pdpUrl", "")
                if isinstance(pdp, dict):
                    pdp = pdp.get("url") or pdp.get("path") or ""
                products.append({
                    "brand": "Nike",
                    "name": name,
                    "image": image,
                    "original_price": round(float(initial), 2),
                    "sale_price": round(float(current), 2),
                    "discount_pct": discount,
                    "url": pdp if pdp.startswith("http") else f"https://www.nike.com{pdp}",
                    "category": p.get("productType", ""),
                    "gender": _parse_gender(subtitle, fallback_gender),
                    "sizes": [],
                    "_id": p.get("productCode") or p.get("globalProductId") or name,
                })
            except Exception:
                continue
    return products


def _fetch_page(url, gender):
    """Fetch a single paginated API page and return its products."""
    try:
        r = requests.get(API_BASE + url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        return _parse_groupings(r.json().get("productGroupings", []), gender)
    except Exception:
        return []


def _fetch_category(start_url, gender):
    products = []

    # Page 1 — from the HTML (has total page count)
    try:
        r = requests.get(start_url, headers=HEADERS, timeout=15)
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not match:
            return products
        data = json.loads(match.group(1))
        wall = data["props"]["pageProps"]["initialState"]["Wall"]
        products.extend(_parse_groupings(wall.get("productGroupings", []), gender))

        page_data = wall.get("pageData", {})
        total_resources = page_data.get("totalResources", 0)
        next_path = page_data.get("next", "")
    except Exception as e:
        print(f"Nike {gender} initial load error: {e}")
        return products

    if not next_path or not total_resources:
        return products

    # Build all remaining page URLs upfront using anchor stepping
    # Extract base URL and count from the next_path
    count = 24
    base_url = next_path.split("anchor=")[0]
    # We know anchor=24 is page 2; generate all remaining anchors
    anchors = list(range(24, total_resources, count))

    # Fetch all pages concurrently (cap at 20 workers to be respectful)
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(_fetch_page, f"{base_url}anchor={anchor}&count={count}", gender): anchor
            for anchor in anchors
        }
        for future in as_completed(futures):
            products.extend(future.result())

    return products


def fetch_sale_products():
    seen = set()
    all_products = []

    for url, gender in SALE_CATEGORIES:
        items = _fetch_category(url, gender)
        for p in items:
            uid = p.pop("_id", p["name"])
            if uid not in seen:
                seen.add(uid)
                all_products.append(p)

    return all_products
