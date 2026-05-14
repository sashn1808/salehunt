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
CONSUMER_CHANNEL = "d9a5bc42-4b9c-4976-858a-f159cf99c647"
BASE_WALL = f"/discover/product_wall/v1/marketplace/US/language/en/consumerChannelId/{CONSUMER_CHANNEL}"

# These URL patterns were extracted from Nike's own __NEXT_DATA__ API responses.
# The path and attributeIds are stable identifiers for the sale + gender categories.
SALE_CATEGORIES = [
    (
        f"{BASE_WALL}?path=/w/mens-sale-3yaepznik1"
        f"&attributeIds=0f64ecc7-d624-4e91-b171-b83a03dd8550,5b21a62a-0503-400c-8336-3ccfbff2a684"
        f"&queryType=PRODUCTS&count=24&anchor=0",
        "Men",
    ),
    (
        f"{BASE_WALL}?path=/w/sale-3yaep"
        f"&attributeIds=5b21a62a-0503-400c-8336-3ccfbff2a684"
        f"&queryType=PRODUCTS&count=24&anchor=0",
        "Women",
    ),
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


def _fetch_page(api_path, gender):
    """Fetch a single paginated API page and return its products."""
    try:
        r = requests.get(API_BASE + api_path, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        return _parse_groupings(r.json().get("productGroupings", []), gender)
    except Exception:
        return []


def _fetch_category(start_api_path, gender):
    """
    Fetch all products for a sale category directly via the Nike product wall API.
    No HTML scraping needed — works from cloud server IPs.
    """
    products = []

    # Page 1 (anchor=0) — fetch directly from the API
    try:
        r = requests.get(API_BASE + start_api_path, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"Nike {gender} page 1 error: HTTP {r.status_code}")
            return products
        d = r.json()
        products.extend(_parse_groupings(d.get("productGroupings", []), gender))

        pages = d.get("pages", {})
        total_resources = pages.get("totalResources", 0)
        next_path = pages.get("next", "")
    except Exception as e:
        print(f"Nike {gender} initial load error: {e}")
        return products

    if not next_path or not total_resources:
        return products

    # Build all remaining page URLs from anchor=24 upward
    count = 24
    base_url = next_path.split("anchor=")[0]
    anchors = list(range(24, total_resources, count))

    print(f"Nike {gender}: {total_resources} total, fetching {len(anchors)} more pages concurrently")

    with ThreadPoolExecutor(max_workers=8) as executor:
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

    for api_path, gender in SALE_CATEGORIES:
        items = _fetch_category(api_path, gender)
        for p in items:
            uid = p.pop("_id", p["name"])
            if uid not in seen:
                seen.add(uid)
                all_products.append(p)

    print(f"Nike total: {len(all_products)} products")
    return all_products
