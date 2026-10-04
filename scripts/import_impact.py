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

IMPACT_ACCOUNT_SID = os.environ.get("IMPACT_ACCOUNT_SID")
IMPACT_AUTH_TOKEN = os.environ.get("IMPACT_AUTH_TOKEN")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)

NETWORK = "Impact"

# --------------------------------------------------
# Sidi catalog settings
# --------------------------------------------------

SIDI_MERCHANT = "Sidi"
SIDI_CATALOG_ID = "33784"
SIDI_PROGRAM_ID = "50060"
SIDI_CATALOG_FILE = "Sidi-US-USD_IR.txt.gz"

# --------------------------------------------------
# Innova catalog settings
# --------------------------------------------------

INNOVA_MERCHANT = "Innova Electronics"
INNOVA_CATALOG_ID = "33598"


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
    print("Catalog ID:", SIDI_CATALOG_ID)
    print("Program ID:", SIDI_PROGRAM_ID)

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

        reader = csv.DictReader(
            file,
            delimiter="\t"
        )

        for row in reader:
            products.append(row)

    print(
        f"Sidi catalog rows read: {len(products)}"
    )

    return products


def load_innova_catalog():
    print("Loading Innova Electronics catalog...")
    print("Catalog ID:", INNOVA_CATALOG_ID)

    if not IMPACT_ACCOUNT_SID:
        raise RuntimeError(
            "IMPACT_ACCOUNT_SID is missing"
        )

    if not IMPACT_AUTH_TOKEN:
        raise RuntimeError(
            "IMPACT_AUTH_TOKEN is missing"
        )

    url = (
        "https://api.impact.com/"
        f"Mediapartners/{IMPACT_ACCOUNT_SID}/"
        f"Catalogs/{INNOVA_CATALOG_ID}/Items"
    )

    headers = {
        "Accept": "application/json"
    }

    params = {
        "PageSize": 1000
    }

    response = requests.get(
        url,
        auth=(
            IMPACT_ACCOUNT_SID,
            IMPACT_AUTH_TOKEN
        ),
        headers=headers,
        params=params,
        timeout=60
    )

    print(
        "Innova API status:",
        response.status_code
    )

    response.raise_for_status()

    data = response.json()

    products = (
        data.get("Items")
        or data.get("Products")
        or data.get("Records")
        or []
    )

    print(
        f"Innova catalog rows read: {len(products)}"
    )

    return products


def normalize_product(row, merchant):
    external_id = find_value(
        row,
        "Unique Merchant SKU",
        "UniqueMerchantSKU",
        "SKU",
        "Product ID",
        "ProductId",
        "Product Id",
        "Catalog Item ID",
        "CatalogItemId",
        "Id"
    )

    title = find_value(
        row,
        "Product Name",
        "ProductName",
        "Name",
        "Title"
    )

    affiliate_url = find_value(
        row,
        "Product URL",
        "ProductUrl",
        "URL",
        "Url",
        "Tracking URL",
        "TrackingUrl"
    )

    if (
        not external_id
        or not title
        or not affiliate_url
    ):
        return None

    description = find_value(
        row,
        "Product Description",
        "ProductDescription",
        "Description"
    )

    category = find_value(
        row,
        "Category",
        "Product Category",
        "ProductCategory"
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
    ) or merchant

    image_url = find_value(
        row,
        "Image URL",
        "Image Url",
        "ImageURL",
        "ImageUrl"
    )

    price = to_number(
        find_value(
            row,
            "Current Price",
            "CurrentPrice",
            "Price",
            "Sale Price",
            "SalePrice"
        )
    )

    currency = find_value(
        row,
        "Currency"
    ) or "USD"

    availability = find_value(
        row,
        "Stock Availability",
        "StockAvailability",
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
        "merchant": merchant,
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


def prepare_products(
    raw_products,
    merchant
):
    normalized = []
    skipped = 0

    for row in raw_products:
        product = normalize_product(
            row,
            merchant
        )

        if product is None:
            skipped += 1
            continue

        normalized.append(product)

    print(
        f"{merchant} normalized:",
        len(normalized)
    )

    print(
        f"{merchant} skipped:",
        skipped
    )

    unique = {}

    for product in normalized:
        key = (
            product["network"],
            product["external_id"]
        )
        unique[key] = product

    products = list(unique.values())

    print(
        f"{merchant} unique products:",
        len(products)
    )

    return products


def upsert_products(
    products,
    merchant
):
    batch_size = 100
    imported = 0

    for start in range(
        0,
        len(products),
        batch_size
    ):
        batch = products[
            start:start + batch_size
        ]

        supabase.table(
            "products"
        ).upsert(
            batch,
            on_conflict="network,external_id"
        ).execute()

        imported += len(batch)

        print(
            f"{merchant}: "
            f"upserted "
            f"{imported}/{len(products)}"
        )

    return imported


def main():
    # ----------------------------------------------
    # Sidi
    # ----------------------------------------------

    sidi_raw = load_sidi_catalog()

    sidi_products = prepare_products(
        sidi_raw,
        SIDI_MERCHANT
    )

    sidi_imported = upsert_products(
        sidi_products,
        SIDI_MERCHANT
    )

    # ----------------------------------------------
    # Innova Electronics
    # ----------------------------------------------

    innova_raw = load_innova_catalog()

    innova_products = prepare_products(
        innova_raw,
        INNOVA_MERCHANT
    )

    innova_imported = upsert_products(
        innova_products,
        INNOVA_MERCHANT
    )

    print("----------------------------------------")
    print("IMPACT IMPORT COMPLETE")
    print(
        "Sidi imported/updated:",
        sidi_imported
    )
    print(
        "Innova imported/updated:",
        innova_imported
    )
    print("----------------------------------------")


if __name__ == "__main__":
    main()
