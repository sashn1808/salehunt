"""
Run all brand scrapers and write a single products.json file.
Designed to be executed by GitHub Actions on a schedule (or manually).
"""
import json
import os
import sys
import time

# Make scrapers importable regardless of where we run from
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from scrapers.nike import fetch_sale_products as nike_fetch
from scrapers.reebok import fetch_sale_products as reebok_fetch


def main():
    started = time.time()
    products = []
    errors = {}
    by_brand = {}

    for name, fn in [("Nike", nike_fetch), ("Reebok", reebok_fetch)]:
        try:
            t0 = time.time()
            items = fn()
            by_brand[name] = len(items)
            products.extend(items)
            print(f"✓ {name}: {len(items)} items ({time.time()-t0:.1f}s)")
        except Exception as e:
            errors[name] = str(e)
            print(f"✗ {name} failed: {e}")

    # Sort by discount % desc so the most attractive deals are first
    products.sort(key=lambda p: p.get("discount_pct", 0), reverse=True)

    output = {
        "products": products,
        "total": len(products),
        "by_brand": by_brand,
        "errors": errors,
        "updated_at": int(time.time()),
    }

    out_path = os.path.join(ROOT, "products.json")
    with open(out_path, "w", encoding="utf-8") as f:
        # No indent => smaller file; faster CDN delivery
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\n→ wrote {out_path}  ({len(products):,} products, {size_kb:.0f} KB, total {time.time()-started:.1f}s)")


if __name__ == "__main__":
    main()
