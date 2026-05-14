from flask import Flask, jsonify, render_template
import threading
import time

app = Flask(__name__)

# Simple in-memory cache: {brand: {products: [...], fetched_at: timestamp}}
_cache = {}
_cache_ttl = 1800  # 30 minutes


def _get_cached(brand):
    entry = _cache.get(brand)
    if entry and (time.time() - entry["fetched_at"]) < _cache_ttl:
        return entry["products"]
    return None


def _set_cache(brand, products):
    _cache[brand] = {"products": products, "fetched_at": time.time()}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/products")
def all_products():
    results = []
    errors = {}

    def fetch_brand(brand_name, fetch_fn):
        cached = _get_cached(brand_name)
        if cached is not None:
            results.extend(cached)
            return
        try:
            items = fetch_fn()
            _set_cache(brand_name, items)
            results.extend(items)
        except Exception as e:
            errors[brand_name] = str(e)

    from scrapers.nike import fetch_sale_products as nike_fetch
    from scrapers.reebok import fetch_sale_products as reebok_fetch
    from scrapers.hm import fetch_sale_products as hm_fetch

    threads = [
        threading.Thread(target=fetch_brand, args=("Nike", nike_fetch)),
        threading.Thread(target=fetch_brand, args=("Reebok", reebok_fetch)),
        threading.Thread(target=fetch_brand, args=("H&M", hm_fetch)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    # Sort by discount % descending
    results.sort(key=lambda x: x.get("discount_pct", 0), reverse=True)

    return jsonify({"products": results, "errors": errors, "total": len(results)})


@app.route("/api/products/<brand>")
def brand_products(brand):
    brand_map = {
        "nike": ("Nike", "scrapers.nike", "fetch_sale_products"),
        "reebok": ("Reebok", "scrapers.reebok", "fetch_sale_products"),
        "hm": ("H&M", "scrapers.hm", "fetch_sale_products"),
    }
    key = brand.lower().replace("&", "").replace(" ", "")
    if key not in brand_map:
        return jsonify({"error": "Unknown brand"}), 404

    brand_name, module_path, fn_name = brand_map[key]
    cached = _get_cached(brand_name)
    if cached is not None:
        return jsonify({"products": cached, "total": len(cached)})

    import importlib
    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name)
    products = fn()
    _set_cache(brand_name, products)
    return jsonify({"products": products, "total": len(products)})


@app.route("/api/cache/clear")
def clear_cache():
    _cache.clear()
    return jsonify({"status": "cleared"})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
