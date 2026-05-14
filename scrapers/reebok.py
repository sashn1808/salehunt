import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def _parse_gender(tags):
    tags_lower = [t.lower() for t in tags]
    if "category-mens" in tags_lower:
        return "Men"
    if "category-womens" in tags_lower:
        return "Women"
    if any(t in tags_lower for t in ["category-kids", "category-boys", "category-girls"]):
        return "Kids"
    if "unisex" in tags_lower:
        return "Unisex"
    return "Unisex"

def _parse_sizes(options):
    for opt in options:
        if opt.get("name", "").lower() == "size":
            return opt.get("values", [])
    return []

def fetch_sale_products():
    products = []
    page = 1
    while True:
        try:
            url = f"https://www.reebok.com/collections/sale/products.json?page={page}&limit=30"
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                print(f"Reebok page {page} HTTP {r.status_code}, stopping")
                break
            data = r.json()
            items = data.get("products", [])
            if not items:
                break
            for item in items:
                for variant in item.get("variants", []):
                    original = variant.get("compare_at_price")
                    sale = variant.get("price")
                    if original and sale and float(original) > float(sale):
                        original_f = float(original)
                        sale_f = float(sale)
                        discount = round((1 - sale_f / original_f) * 100)
                        image = None
                        if item.get("images"):
                            src = item["images"][0]["src"]
                            image = "https:" + src if src.startswith("//") else src
                        products.append({
                            "brand": "Reebok",
                            "name": item.get("title", ""),
                            "image": image,
                            "original_price": round(original_f, 2),
                            "sale_price": round(sale_f, 2),
                            "discount_pct": discount,
                            "url": f"https://www.reebok.com/products/{item.get('handle', '')}",
                            "category": item.get("product_type", ""),
                            "gender": _parse_gender(item.get("tags", [])),
                            "sizes": _parse_sizes(item.get("options", [])),
                        })
                        break
            page += 1
        except Exception as e:
            print(f"Reebok page {page} error: {e}")
            break
    print(f"Reebok total: {len(products)} products")
    return products
