import os
import requests

IMPACT_ACCOUNT_SID = os.environ["IMPACT_ACCOUNT_SID"]
IMPACT_AUTH_TOKEN = os.environ["IMPACT_AUTH_TOKEN"]

url = (
    "https://api.impact.com/Mediapartners/"
    f"{IMPACT_ACCOUNT_SID}/Catalogs"
)

response = requests.get(
    url,
    auth=(IMPACT_ACCOUNT_SID, IMPACT_AUTH_TOKEN),
    headers={
        "Accept": "application/json",
        "Impact-Version": "16"
    },
    timeout=60
)

print("HTTP status:", response.status_code)

if response.status_code != 200:
    print(response.text[:1000])
    raise SystemExit(1)

data = response.json()
catalogs = data.get("Catalogs") or []

print(f"CATALOGS FOUND: {len(catalogs)}")
print("----------------------------------------")

for catalog in catalogs:
    print("Name:", catalog.get("Name"))
    print("Catalog ID:", catalog.get("Id"))
    print("Campaign:", catalog.get("CampaignName"))
    print("Campaign ID:", catalog.get("CampaignId"))
    print("Products:", catalog.get("NumberOfItems"))
    print("Currency:", catalog.get("Currency"))
    print("Items URI:", catalog.get("ItemsUri"))
    print("----------------------------------------")
