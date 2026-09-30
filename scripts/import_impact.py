import os
import requests
from supabase import create_client


# =========================================================
# Configuration
# =========================================================

IMPACT_ACCOUNT_SID = os.environ["IMPACT_ACCOUNT_SID"]
IMPACT_AUTH_TOKEN = os.environ["IMPACT_AUTH_TOKEN"]

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

IMPACT_API_BASE = "https://api.impact.com"

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# =========================================================
# Impact catalogs to import
# =========================================================

BRANDS = [
    {
        "name": "Chefman",
        "program_id": "49263",
        "catalog_id": "34536",
    },
    {
        "name": "DOWAN LLC",
        "program_id": "51140",
        "catalog_id": "32698",
    },
    {
        "name": "Sidi",
        "program_id": "50060",
        "catalog_id": "33784",
    },
]


# =========================================================
# Helpers
# =========================================================

def first_value(data, *keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = data.get(key)

        if value is not None and value != "":
            return value

    return None


def to_number(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_integer(value):
    if value is None or value == "":
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# =========================================================
# Impact Catalog Items API
# =========================================================

def get_products(brand):

    program_id = brand["program_id"]
    catalog_id = brand["catalog_id"]
    brand_name = brand["name"]

    url = (
        f"{IMPACT_API_BASE}/Mediapartners/"
        f"{IMPACT_ACCOUNT_SID}/Catalogs/"
        f"{catalog_id}/Items"
    )

    # Impact documents Page/PageSize pagination for catalog
    # item searching. Start with 250 items per page.
    page_size = 250
    page = 1
    products = []

    print("----------------------------------------")
    print(f"Connecting to Impact Catalog: {brand_name}")
    print(f"Program: {program_id}")
    print(f"Catalog: {catalog_id}")

    while True:

        params = {
            "Page": page,
            "PageSize": page_size,
        }

        response = requests.get(
            url,
            auth=(
                IMPACT_ACCOUNT_SID,
                IMPACT_AUTH_TOKEN
            ),
            headers={
                "Accept": "application/json",
                "Impact-Version": "16"
            },
            params=params,
            timeout=120
        )

        if response.status_code != 200:
            print(
                f"Impact Catalog API request failed "
                f"for {brand_name}."
            )
            print(
                "HTTP status:",
                response.status_code
            )
            print(response.text[:1000])
            return []

        data = response.json()

        batch = data.get("Items") or []

        if not batch:
            break

        for item in batch:
            item["_import_brand_name"] = brand_name
            item["_import_program_id"] = program_id
            item["_import_catalog_id"] = catalog_id

        products.extend(batch)

        print(
            f"Retrieved page {page}: "
            f"{len(batch)} products "
            f"({len(products)} total)"
        )

        # Use API pagination metadata when supplied.
        total_pages = data.get("TotalPages")

        if total_pages:
            try:
                if page >= int(total_pages):
                    break
            except (TypeError, ValueError):
                pass

        # A partial page means we reached the end.
        if len(batch) < page_size:
            break

        page += 1

        # Safety guard. 1000 pages at 250/page is
        # far beyond the current catalogs.
        if page > 1000:
            raise RuntimeError(
                f"Pagination safety limit reached "
                f"for {brand_name}."
            )

    print(
        f"{brand_name}: "
        f"{len(products)} catalog items retrieved."
    )

    return products


# =========================================================
# Normalize Impact Catalog Item
# =========================================================

def normalize_product(item):

    import_brand_name = item.get(
        "_import_brand_name",
        "Impact Merchant"
    )

    external_id = first_value(
        item,
        "CatalogItemId",
        "Id"
    )

    title = first_value(
        item,
        "Name"
    )

    # IMPORTANT:
    # Impact Catalog API documents "Url" as the tracking
    # URL unique to the partner account.
    affiliate_url = first_value(
        item,
        "Url",
        "MobileUrl"
    )

    if not external_id:
        return None

    if not title:
        return None

    if not affiliate_url:
        return None

    merchant = (
        first_value(
            item,
            "CampaignName"
        )
        or import_brand_name
    )

    brand = (
        first_value(
            item,
            "Manufacturer"
        )
        or import_brand_name
    )

    description = first_value(
        item,
        "Description"
    )

    category = first_value(
        item,
        "Category",
        "OriginalFormatCategory"
    )

    subcategory = first_value(
        item,
        "SubCategory"
    )

    image_url = first_value(
        item,
        "ImageUrl"
    )

    price = to_number(
        first_value(
            item,
            "CurrentPrice",
            "OriginalPrice"
        )
    )

    currency = (
        first_value(
            item,
            "Currency"
        )
        or "USD"
    )

    availability = first_value(
        item,
        "StockAvailability"
    )

    sku = (
        first_value(
            item,
            "Mpn"
        )
        or first_value(
            item,
            "CatalogItemId"
        )
    )

    upc = first_value(
        item,
        "Gtin"
    )

    # The Catalog API does not document dedicated
    # rating/review-count fields in the standard model.
    rating = None
    review_count = None

    # The catalog's Url is already an Impact tracking URL.
    # Store it as both the click destination and affiliate URL.
    product_url = affiliate_url

    return {
        "external_id": str(external_id),
        "network": "IMPACT",
        "merchant": str(merchant),
        "title": str(title),
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


# =========================================================
# Supabase
# =========================================================

def import_into_supabase(products):

    normalized = []
    skipped = 0

    for item in products:

        product = normalize_product(item)

        if product:
            normalized.append(product)
        else:
            skipped += 1

    print("----------------------------------------")
    print(
        f"Products normalized: "
        f"{len(normalized)}"
    )

    print(
        f"Skipped products: "
        f"{skipped}"
    )

    if not normalized:
        raise RuntimeError(
            "No products were normalized. "
            "Stopping before changing the database."
        )

    # Remove duplicate network + external_id combinations
    # before sending records to Supabase.

    unique_products = {}
    duplicate_count = 0

    for product in normalized:

        key = (
            product["network"],
            product["external_id"]
        )

        if key in unique_products:
            duplicate_count += 1

        unique_products[key] = product

    normalized = list(
        unique_products.values()
    )

    print(
        f"Duplicate products removed: "
        f"{duplicate_count}"
    )

    print(
        f"Unique products ready for Supabase: "
        f"{len(normalized)}"
    )

    batch_size = 100

    for start in range(
        0,
        len(normalized),
        batch_size
    ):

        batch = normalized[
            start:start + batch_size
        ]

        supabase.table("products").upsert(
            batch,
            on_conflict="network,external_id"
        ).execute()

        completed = min(
            start + batch_size,
            len(normalized)
        )

        print(
            f"Upserted "
            f"{completed}/"
            f"{len(normalized)} products"
        )

    return len(normalized)


# =========================================================
# Main
# =========================================================

def main():

    print("----------------------------------------")
    print("Affiliate Marketplace - Impact Importer")
    print("----------------------------------------")

    all_products = []

    for brand in BRANDS:

        products = get_products(brand)

        if not products:
            print(
                f"WARNING: Impact returned zero "
                f"catalog items for {brand['name']}."
            )
            continue

        all_products.extend(products)

    print("----------------------------------------")

    print(
        f"Total products retrieved from Impact: "
        f"{len(all_products)}"
    )

    if not all_products:
        raise RuntimeError(
            "Impact returned zero products for all "
            "configured catalogs. "
            "No database changes were made."
        )

    imported = import_into_supabase(
        all_products
    )

    print("----------------------------------------")
    print("IMPORT COMPLETE")

    print(
        f"Imported/updated: "
        f"{imported}"
    )

    print("----------------------------------------")


if __name__ == "__main__":
    main()
