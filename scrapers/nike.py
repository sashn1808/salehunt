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

def _wall_url(marketplace, language, path, attribute_ids):
    base = f"/discover/product_wall/v1/marketplace/{marketplace}/language/{language}/consumerChannelId/{CONSUMER_CHANNEL}"
    return f"{base}?path={path}&attributeIds={attribute_ids}&queryType=PRODUCTS&count=24&anchor=0"

# Each entry: (api_start_url, gender, country_label, currency_symbol, site_base_url)
SALE_CATEGORIES = [
    # --- United States ---
    (
        _wall_url("US", "en", "/w/mens-sale-3yaepznik1",
                  "0f64ecc7-d624-4e91-b171-b83a03dd8550,5b21a62a-0503-400c-8336-3ccfbff2a684"),
        "Men", "US", "$", "https://www.nike.com",
    ),
    (
        _wall_url("US", "en", "/w/sale-3yaep",
                  "5b21a62a-0503-400c-8336-3ccfbff2a684"),
        "Women", "US", "$", "https://www.nike.com",
    ),
    # Note: Nike does not operate a direct India marketplace — nike.com/in
    # redirects to nike.in (a 3rd-party reseller), and the IN API returns 0
    # products. Same for many other markets. Adding more countries requires
    # finding a brand+region combo that actually sells direct.
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


def _parse_groupings(groupings, fallback_gender, country, currency_symbol, site_base):
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
                if not pdp.startswith("http"):
                    pdp = f"{site_base}{pdp}"
                products.append({
                    "brand": "Nike",
                    "name": name,
                    "image": image,
                    "original_price": round(float(initial), 2),
                    "sale_price": round(float(current), 2),
                    "discount_pct": discount,
                    "url": pdp,
                    "category": p.get("productType", ""),
                    "gender": _parse_gender(subtitle, fallback_gender),
                    "sizes": [],
                    "country": country,
                    "currency_symbol": currency_symbol,
                    "_id": f"{country}_{p.get('productCode') or p.get('globalProductId') or name}",
                })
            except Exception:
                continue
    return products


def _fetch_page(api_path, gender, country, currency_symbol, site_base):
    try:
        r = requests.get(API_BASE + api_path, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        return _parse_groupings(r.json().get("productGroupings") or [], gender, country, currency_symbol, site_base)
    except Exception:
        return []


def _fetch_category(start_api_path, gender, country, currency_symbol, site_base):
    products = []

    try:
        r = requests.get(API_BASE + start_api_path, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"Nike {country}/{gender} page 1 error: HTTP {r.status_code}")
            return products
        d = r.json()
        products.extend(_parse_groupings(d.get("productGroupings") or [], gender, country, currency_symbol, site_base))

        pages = d.get("pages", {})
        total_resources = pages.get("totalResources", 0)
        next_path = pages.get("next", "")
    except Exception as e:
        print(f"Nike {country}/{gender} initial load error: {e}")
        return products

    if not next_path or not total_resources:
        return products

    count = 24
    base_url = next_path.split("anchor=")[0]
    anchors = list(range(24, total_resources, count))
    print(f"Nike {country}/{gender}: {total_resources} total, fetching {len(anchors)} pages")

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {
            executor.submit(_fetch_page, f"{base_url}anchor={anchor}&count={count}",
                            gender, country, currency_symbol, site_base): anchor
            for anchor in anchors
        }
        for future in as_completed(futures):
            try:
                products.extend(future.result())
            except Exception as e:
                print(f"Nike {country}/{gender} page failed: {e}")

    return products


def fetch_sale_products():
    seen = set()
    all_products = []

    for api_path, gender, country, currency_symbol, site_base in SALE_CATEGORIES:
        items = _fetch_category(api_path, gender, country, currency_symbol, site_base)
        for p in items:
            uid = p.pop("_id", p["name"])
            if uid not in seen:
                seen.add(uid)
                all_products.append(p)

    print(f"Nike total: {len(all_products)} products")
    return all_products
