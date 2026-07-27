"""Fix 3 Odoo building records that got wrong ALS canonical names.

Odoo ID | Wrong name          | Correct name
--------|---------------------|---------------------------
2       | 第二座               | 雅濤閣
10      | 暨尖沙咀消防局        | China Hong Kong City (中港城)
13      | 交易廣塲第一座        | 99廣場

Run:
    cd langgraph
    source .venv/bin/activate
    python scripts/fix_odoo_building_names.py
"""

import os
import sys
import xmlrpc.client
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.utils.als_lookup import lookup_building

ODOO_URL = "https://c21net.odoo.com"
ODOO_DB = "c21net"
ODOO_USERNAME = "admin@c21net.com"
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")
BUILDING_MODEL = "x_c21_building"

FIXES = [
    {
        "odoo_id": 2,
        "wrong_name": "第二座",
        "correct_name": "雅濤閣",
        "als_query": "雅濤閣 觀塘",          # add district to help ALS disambiguate
    },
    {
        "odoo_id": 10,
        "wrong_name": "暨尖沙咀消防局",
        "correct_name": "China Hong Kong City",
        "als_query": "中港城 尖沙咀",         # Chinese name + district
    },
    {
        "odoo_id": 13,
        "wrong_name": "交易廣塲第一座",
        "correct_name": "99廣場",
        "als_query": "99廣場",
    },
]


def connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
    if not uid:
        print("ERROR: Odoo authentication failed")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def fix_building(models, uid, fix: dict):
    odoo_id = fix["odoo_id"]
    correct_name = fix["correct_name"]
    als_query = fix["als_query"]

    print(f"\n[id={odoo_id}] {fix['wrong_name']} → {correct_name}")

    # Try ALS with the better query
    als = lookup_building(als_query)
    if als and als.confidence >= 60:
        print(f"  ALS hit: '{als.name_zh}' / '{als.name_en}' "
              f"geo={als.geo_id} confidence={als.confidence:.1f}")

        # Check if geo_id already used by another record (avoid duplicate)
        if als.geo_id:
            clash = models.execute_kw(
                ODOO_DB, uid, ODOO_API_KEY, BUILDING_MODEL, "search",
                [[["x_als_geo_id", "=", als.geo_id], ["id", "!=", odoo_id]]],
            )
            if clash:
                print(f"  WARNING: geo_id {als.geo_id} already on record id={clash[0]} — "
                      "clearing geo_id to avoid clash")
                als_geo_id_val = False
            else:
                als_geo_id_val = als.geo_id
        else:
            als_geo_id_val = False

        vals = {
            "x_name": als.name_zh or correct_name,
            "x_name_en": als.name_en or "",
            "x_address": als.address_zh or "",
            "x_als_geo_id": als_geo_id_val,
            "x_needs_review": False,
        }
        if als.district_odoo:
            vals["x_district"] = als.district_odoo
        if als.lat is not None:
            vals["x_lat"] = als.lat
        if als.lng is not None:
            vals["x_lng"] = als.lng
    else:
        confidence = als.confidence if als else 0
        print(f"  ALS miss (confidence={confidence:.1f}) — using manual name, clearing geo_id")
        vals = {
            "x_name": correct_name,
            "x_als_geo_id": False,   # clear the wrong geo_id
            "x_needs_review": False,
        }

    models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, BUILDING_MODEL, "write",
                      [[odoo_id], vals])
    print(f"  Updated → x_name='{vals['x_name']}' needs_review=False")


def main():
    if not ODOO_API_KEY:
        print("ERROR: ODOO_API_KEY not set")
        sys.exit(1)

    print("Connecting to Odoo...")
    uid, models = connect()
    print(f"Authenticated (uid={uid})\n")

    for fix in FIXES:
        fix_building(models, uid, fix)

    print("\nDone. Refresh Odoo 大廈列表 Buildings to verify.")


if __name__ == "__main__":
    main()
