import os
import csv
import gzip
import requests
from io import StringIO
from supabase import create_client

# --------------------------------------------------
# Environment variables
# --------------------------------------------------

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

# --------------------------------------------------
# Sidi catalog settings
# --------------------------------------------------

NETWORK = "Impact"
MERCHANT = "Sidi"
CATALOG_ID = "33784"
PROGRAM_ID = "50060"

# This will be replaced with the permanent automated
# Sidi catalog source after the first successful import.
SIDI_CATALOG_FILE = "Sidi-US-USD_IR.txt.gz"


def clean(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def to_number(value):
    value = clean(value)

    if value is None:
        return None

    try:
        value = (
            value.replace("$", "")
            .replace(",", "")
            .strip()
        )
        return float(value)
    except (ValueError, AttributeError):
        return None


def find_value(row, *names):
    for name in names:
        if name in row:
            value = clean(row.get(name))
            if value is not None:
                return value

    return None


def load_sidi_catalog():
    print("Loading Sidi US/USD catalog...")
    print("Catalog ID:", CATALOG_ID)
    print("Program ID:", PROGRAM_ID)

    if not os.path.exists(SIDI_CATALOG_FILE):
        raise FileNotFoundError(
            f"Catalog file not found: {SIDI_CATALOG_FILE}"
        )

    products = []

    with gzip.open(
        SIDI_CATALOG_FILE,
        mode="rt",
        encoding="utf-8-sig",
        errors="replace",
        newline=""
    ) as file:

        reader = csv.DictReader(file, delimiter="\t")

        print("Catalog columns:")
        print(reader.fieldnames)

        for row in reader:
            products.append(row)

    print(f"Sidi catalog rows read: {len(products)}")

    return products


def normalize_product(row):
    external_id = find_value(
        row,
        "Unique Merchant SKU",
        "SKU",
        "Product ID",
        "Product Id",
        "Catalog Item ID",
        "CatalogItemId"
    )

    title = find_value(
        row,
        "Product Name",
        "Name",
        "Title"
    )

    affiliate_url = find_value(
        row,
        "Product URL",
        "URL",
        "Url",
        "Tracking URL"
    )

    if not external_id or not title or not affiliate_url:
        return None

    description = find_value(
        row,
        "Product Description",
        "Description"
    )

    category = find_value(
        row,
        "Category",
        "Product Category"
    )

    subcategory = find_value(
        row,
        "Subcategory",
        "Sub Category",
        "SubCategory"
    )

    brand = find_value(
        row,
        "Manufacturer",
        "Brand"
    ) or MERCHANT

    image_url = find_value(
        row,
        "Image URL",
        "Image Url",
        "ImageURL"
    )

    price = to_number(
        find_value(
            row,
            "Current Price",
            "Price",
            "Sale Price"
        )
    )

    currency = find_value(
        row,
        "Currency"
    ) or "USD"

    availability = find_value(
        row,
        "Stock Availability",
        "Availability",
        "Stock"
    )

    upc = find_value(
        row,
        "GTIN",
        "UPC"
    )

    sku = find_value(
        row,
        "SKU",
        "MPN"
    ) or external_id

    return {
        "external_id": external_id,
        "network": NETWORK,
        "merchant": MERCHANT,
        "title": title,
        "description": description,
        "category": category,
        "subcategory": subcategory,
        "brand": brand,
        "image_url": image_url,
        "product_url": affiliate_url,
        "affiliate_url": affiliate_url,
        "price": price,
        "currency": currency,
        "availability": availability,
        "rating": None,
        "review_count": None,
        "sku": sku,
        "upc": upc,
        "is_active": True,
    }


def main():
    raw_products = load_sidi_catalog()

    normalized = []
    skipped = 0

    for row in raw_products:
        product = normalize_product(row)

        if product is None:
            skipped += 1
            continue

        normalized.append(product)

    print(f"Products normalized: {len(normalized)}")
    print(f"Skipped products: {skipped}")

    # Remove duplicate SKUs before sending to Supabase
    unique = {}

    for product in normalized:
        key = (product["network"], product["external_id"])
        unique[key] = product

    products = list(unique.values())

    print(
        "Duplicate products removed:",
        len(normalized) - len(products)
    )

    print(
        "Unique Sidi products ready for Supabase:",
        len(products)
    )

    batch_size = 100
    imported = 0

    for start in range(0, len(products), batch_size):
        batch = products[start:start + batch_size]

        supabase.table("products").upsert(
            batch,
            on_conflict="network,external_id"
        ).execute()

        imported += len(batch)

        print(
            f"Upserted {imported}/{len(products)}"
        )

    print("----------------------------------------")
    print("SIDI IMPORT COMPLETE")
    print("Imported/updated:", imported)
    print("----------------------------------------")


if __name__ == "__main__":
    main()
