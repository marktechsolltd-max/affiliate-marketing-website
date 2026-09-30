import os
import sys
import time
import requests
from supabase import create_client


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

IMPACT_ACCOUNT_SID = os.environ["IMPACT_ACCOUNT_SID"]
IMPACT_AUTH_TOKEN = os.environ["IMPACT_AUTH_TOKEN"]

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

IMPACT_API_BASE = "https://api.impact.com"

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
]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def first_value(item, *names):
    if not isinstance(item, dict):
        return None

    for name in names:
        value = item.get(name)
        if value is not None and value != "":
            return value

    return None


def to_number(value):
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
# Impact API - Products
# ---------------------------------------------------------

def get_products(brand):

    program_id = brand["program_id"]
    catalog_id = brand["catalog_id"]
    brand_name = brand["name"]

    url = (
        f"{IMPACT_API_BASE}/Mediapartners/"
        f"{IMPACT_ACCOUNT_SID}/Marketplace/Products/"
        f"Programs/{program_id}/Catalogs/{catalog_id}/Products"
    )

    params = {
        "PageSize": 250
    }

    products = []
    page = 1

    print("----------------------------------------")
    print(f"Connecting to Impact: {brand_name}")
    print(f"Program: {program_id}")
    print(f"Catalog: {catalog_id}")

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
            print(f"Impact API request failed for {brand_name}.")
            print("HTTP status:", response.status_code)
            print(response.text[:1000])
            return []

        data = response.json()

        batch = data.get("Results") or []

        if not batch:
            break

        for item in batch:
            item["_import_brand_name"] = brand_name
            item["_import_program_id"] = program_id

        products.extend(batch)

        print(
            f"Retrieved page {page}: "
            f"{len(batch)} products "
            f"({len(products)} total)"
        )

        total_pages = data.get("TotalPages")

        if total_pages:
            try:
                if page >= int(total_pages):
                    break
            except (TypeError, ValueError):
                pass

        if len(batch) < params["PageSize"]:
            break

        page += 1

        if page > 1000:
            raise RuntimeError(
                f"Pagination safety limit reached for {brand_name}."
            )

    print(
        f"{brand_name}: "
        f"{len(products)} products retrieved."
    )

    return products


# ---------------------------------------------------------
# Impact API - Tracking Links
# ---------------------------------------------------------

def create_tracking_link(offer, program_id):

    destination_url = first_value(
        offer,
        "OriginalUrl",
        "Url"
    )

    if not destination_url:
        return None

    tracking_url = (
        f"{IMPACT_API_BASE}/Mediapartners/"
        f"{IMPACT_ACCOUNT_SID}/Programs/"
        f"{program_id}/TrackingLinks"
    )

    payload = {
        "DeepLink": destination_url
    }

    response = requests.post(
        tracking_url,
        auth=(IMPACT_ACCOUNT_SID, IMPACT_AUTH_TOKEN),
        headers={
            "Accept": "application/json",
            "Impact-Version": "16"
        },
        data=payload,
        timeout=60
    )

    if response.status_code not in (200, 201):
        print(
            "Tracking link generation failed "
            f"for SKU {offer.get('Sku')}."
        )
        print("HTTP status:", response.status_code)
        print(response.text[:500])
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    tracking_link = first_value(
        data,
        "TrackingURL",
        "TrackingUrl",
        "Url",
        "URL",
        "ShortUrl",
        "ShortURL"
    )

    return tracking_link


# ---------------------------------------------------------
# Normalize Impact product
# ---------------------------------------------------------

def normalize_product(item):

    import_brand_name = item.get(
        "_import_brand_name",
        "Impact Merchant"
    )

    program_id = item.get("_import_program_id")

    if not program_id:
        return None

    offers = item.get("Offers") or []

    if not offers:
        return None

    offer = offers[0]

    external_id = (
        first_value(
            offer,
            "CatalogItemId",
            "Sku"
        )
        or first_value(
            item,
            "Id"
        )
    )

    title = (
        first_value(
            item,
            "Name",
            "ProductName",
            "Title"
        )
        or first_value(
            offer,
            "Name"
        )
    )

    product_url = first_value(
        offer,
        "OriginalUrl",
        "Url"
    )

    if not external_id or not title or not product_url:
        return None

    program = offer.get("Program") or {}

    merchant = (
        program.get("Name")
        or import_brand_name
    ).strip()

    product_brand = item.get("ProductBrand") or {}
    manufacturer = item.get("Manufacturer") or {}

    brand = (
        product_brand.get("Name")
        or manufacturer.get("Name")
        or import_brand_name
    )

    description = first_value(
        offer,
        "Description"
    )

    category_data = item.get("Category") or {}

    if isinstance(category_data, dict):
        category = (
            category_data.get("Path")
            or category_data.get("Name")
        )
    else:
        category = (
            str(category_data)
            if category_data
            else None
        )

    labels = (
        offer.get("Labels")
        or item.get("Labels")
        or []
    )

    if isinstance(labels, list) and labels:
        subcategory = str(labels[0])
    else:
        subcategory = None

    image_url = (
        first_value(
            offer,
            "ImageUrl"
        )
        or first_value(
            item,
            "ImageUrl",
            "ImageURL",
            "ImageUri",
            "Image"
        )
    )

    price = to_number(
        first_value(
            offer,
            "CurrentPrice",
            "DollarPrice"
        )
        or first_value(
            item,
            "BestPrice"
        )
    )

    currency = (
        first_value(
            offer,
            "Currency"
        )
        or first_value(
            item,
            "Currency"
        )
        or "USD"
    )

    availability = first_value(
        offer,
        "StockAvailability"
    )

    if availability is None:

        in_stock = item.get(
            "ContainsOfferInStock"
        )

        if in_stock is True:
            availability = "In Stock"

        elif in_stock is False:
            availability = "Out of Stock"

    sku = first_value(
        offer,
        "Sku"
    )

    upc = first_value(
        offer,
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

    print(
        f"[{import_brand_name}] Generating tracking link: "
        f"{title[:60]}"
    )

    affiliate_url = create_tracking_link(
        offer,
        program_id
    )

    if not affiliate_url:
        print(
            "No tracking link generated; "
            "product skipped."
        )
        return None

    time.sleep(0.1)

    return {
        "external_id": str(external_id),
        "network": "IMPACT",
        "merchant": merchant,
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

    # -----------------------------------------------------
    # Remove duplicate network + external_id combinations
    # before Supabase upsert.
    # -----------------------------------------------------

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


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    print("----------------------------------------")
    print("Affiliate Marketplace - Impact Importer")
    print("----------------------------------------")

    all_products = []

    for brand in BRANDS:

        products = get_products(brand)

        if not products:
            print(
                f"WARNING: Impact returned zero products "
                f"for {brand['name']}."
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
            "Impact returned zero products for all configured brands. "
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
