import os
import sys
import requests
from supabase import create_client

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

IMPACT_ACCOUNT_SID = os.environ["IMPACT_ACCOUNT_SID"]
IMPACT_AUTH_TOKEN = os.environ["IMPACT_AUTH_TOKEN"]

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

# Chefman
PROGRAM_ID = "49263"
CATALOG_ID = "34536"

IMPACT_API_BASE = "https://api.impact.com"

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def first_value(item, *names):
    """Return the first non-empty value found."""
    for name in names:
        value = item.get(name)
        if value is not None and value != "":
            return value
    return None


def to_number(value):
    """Convert an API price value to a numeric value when possible."""
    if value is None or value == "":
        return None

    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def to_integer(value):
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------
# Impact API
# ---------------------------------------------------------

def get_chefman_products():
  url = (
    f"{IMPACT_API_BASE}/Mediapartners/"
    f"{IMPACT_ACCOUNT_SID}/Catalogs/{CATALOG_ID}/Items"
)

def get_chefman_products():
    url = (
        f"{IMPACT_API_BASE}/Mediapartners/"
        f"{IMPACT_ACCOUNT_SID}/Marketplace/Products/"
        f"Programs/{PROGRAM_ID}/Catalogs/{CATALOG_ID}/Products"
    )


    params = {
        "PageSize": 250
    }

    products = []
    page = 1

    products = []
    page = 1

    print("Connecting to Impact...")
    print(f"Program: {PROGRAM_ID}")
    print(f"Catalog: {CATALOG_ID}")

    while True:
        params["Page"] = page

        response = requests.get(
            url,
            auth=(IMPACT_ACCOUNT_SID, IMPACT_AUTH_TOKEN),
            headers={
                "Accept": "application/json",
                "Impact-Version": "16"
            },
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print("Impact API request failed.")
            print("HTTP status:", response.status_code)
            print(response.text[:1000])
            sys.exit(1)

        data = response.json()

        print("Impact response keys:", list(data.keys()))
        print("Impact response preview:", str(data)[:3000])

        batch = (
            data.get("Results")
            or
            data.get("Products")
            or data.get("Items")
            or data.get("Records")
            or []
        )

        if not batch:
            break

        products.extend(batch)

        print(
            f"Retrieved page {page}: "
            f"{len(batch)} products "
            f"({len(products)} total)"
        )

        # Stop when the final partial page is reached.
        if len(batch) < params["PageSize"]:
            break

        page += 1

        # Safety guard against accidental infinite pagination.
        if page > 1000:
            raise RuntimeError("Pagination safety limit reached.")

    return products


# ---------------------------------------------------------
# Normalize Impact product -> Supabase product
# ---------------------------------------------------------

def normalize_product(item):

    external_id = first_value(
        item,
        "Id",
        "ProductId",
        "CatalogItemId",
        "UniqueMerchantSKU",
        "Sku",
        "SKU"
    )

    title = first_value(
        item,
        "Name",
        "ProductName",
        "Title"
    )

    affiliate_url = first_value(
        item,
        "TrackingLink",
        "TrackingUrl",
        "Url",
        "ProductUrl",
        "ProductURL"
    )

    if not external_id or not title or not affiliate_url:
        return None

    merchant = first_value(
        item,
        "AdvertiserName",
        "ProgramName",
        "MerchantName",
        "Brand"
    ) or "Chefman"

    brand = first_value(
        item,
        "Brand",
        "Manufacturer"
    ) or "Chefman"

    description = first_value(
        item,
        "Description",
        "ProductDescription"
    )

    category = first_value(
        item,
        "Category",
        "ProductCategory",
        "ProductType"
    )

    subcategory = first_value(
        item,
        "SubCategory",
        "Subcategory"
    )

    image_url = first_value(
        item,
        "ImageUrl",
        "ImageURL",
        "ImageUri",
        "Image"
    )

    product_url = first_value(
        item,
        "LandingPageUrl",
        "ProductUrl",
        "ProductURL"
    )

    price = to_number(
        first_value(
            item,
            "CurrentPrice",
            "Price",
            "SalePrice"
        )
    )

    currency = first_value(
        item,
        "Currency",
        "CurrencyCode"
    ) or "USD"

    availability = first_value(
        item,
        "StockAvailability",
        "Availability",
        "StockStatus"
    )

    sku = first_value(
        item,
        "UniqueMerchantSKU",
        "Sku",
        "SKU"
    )

    upc = first_value(
        item,
        "UPC",
        "Upc",
        "GTIN",
        "Gtin"
    )

    rating = to_number(
        first_value(
            item,
            "Rating",
            "AverageRating"
        )
    )

    review_count = to_integer(
        first_value(
            item,
            "ReviewCount",
            "NumberOfReviews"
        )
    )

    return {
        "external_id": str(external_id),
        "network": "IMPACT",
        "merchant": merchant,
        "title": title,
        "description": description,
        "category": category,
        "subcategory": subcategory,
        "brand": brand,
        "image_url": image_url,
        "product_url": product_url,
        "affiliate_url": affiliate_url,
        "price": price,
        "currency": currency,
        "availability": availability,
        "rating": rating,
        "review_count": review_count,
        "sku": sku,
        "upc": upc,
        "is_active": True
    }


# ---------------------------------------------------------
# Supabase
# ---------------------------------------------------------

def import_into_supabase(products):

    normalized = []
    skipped = 0

    for item in products:
        product = normalize_product(item)

        if product:
            normalized.append(product)
        else:
            skipped += 1

    print(f"Products ready for Supabase: {len(normalized)}")
    print(f"Skipped incomplete products: {skipped}")

    if not normalized:
        raise RuntimeError(
            "No products were normalized. "
            "Stopping before changing the database."
        )

    batch_size = 100

    for start in range(0, len(normalized), batch_size):
        batch = normalized[start:start + batch_size]

        supabase.table("products").upsert(
            batch,
            on_conflict="network,external_id"
        ).execute()

        print(
            f"Upserted {min(start + batch_size, len(normalized))}"
            f"/{len(normalized)} products"
        )

    return len(normalized)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    print("----------------------------------------")
    print("Affiliate Marketplace - Impact Importer")
    print("----------------------------------------")

    products = get_chefman_products()

    print(f"Total products retrieved from Impact: {len(products)}")

    if len(products) == 0:
        raise RuntimeError(
            "Impact returned zero Chefman products. "
            "No database changes were made."
        )

    imported = import_into_supabase(products)

    print("----------------------------------------")
    print("IMPORT COMPLETE")
    print(f"Imported/updated: {imported}")
    print("----------------------------------------")


if __name__ == "__main__":
    main()
