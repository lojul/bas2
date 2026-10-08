"""One-time setup: create x_c21_building model in Odoo with list/form views and menu.

Also adds x_building_id Many2one field to existing x_c21_listing.

Run once:
    cd langgraph
    source .venv/bin/activate
    python scripts/setup_odoo_building_model.py
"""

import os
import sys
import xmlrpc.client
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = "https://c21net.odoo.com"
ODOO_DB = "c21net"
ODOO_USERNAME = "admin@c21net.com"
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")

DISTRICT_SELECTION = [
    ["central", "中環 Central"],
    ["sheung_wan", "上環 Sheung Wan"],
    ["wan_chai", "灣仔 Wan Chai"],
    ["causeway_bay", "銅鑼灣 Causeway Bay"],
    ["quarry_bay", "鰂魚涌 Quarry Bay"],
    ["tsim_sha_tsui", "尖沙咀 Tsim Sha Tsui"],
    ["mong_kok", "旺角 Mong Kok"],
    ["kwun_tong", "觀塘 Kwun Tong"],
    ["kowloon_bay", "九龍灣 Kowloon Bay"],
    ["san_po_kong", "新蒲崗 San Po Kong"],
    ["hung_hom", "紅磡 Hung Hom"],
    ["wong_tai_sin", "黃大仙 Wong Tai Sin"],
    ["cheung_sha_wan", "長沙灣 Cheung Sha Wan"],
    ["kwai_chung", "葵涌 Kwai Chung"],
    ["kwai_fong", "葵芳 Kwai Fong"],
    ["tsuen_wan", "荃灣 Tsuen Wan"],
    ["tuen_mun", "屯門 Tuen Mun"],
    ["yuen_long", "元朗 Yuen Long"],
    ["sha_tin", "沙田 Sha Tin"],
    ["tai_po", "大埔 Tai Po"],
    ["tseung_kwan_o", "將軍澳 Tseung Kwan O"],
    ["ma_on_shan", "馬鞍山 Ma On Shan"],
    ["other", "其他 Other"],
]

PROPERTY_TYPE_SELECTION = [
    ["office", "寫字樓 Office"],
    ["retail", "商舖 Retail"],
    ["ground_shop", "地舖 Ground Shop"],
    ["industrial", "工廈 Industrial"],
    ["residential", "住宅 Residential"],
    ["mixed", "綜合 Mixed"],
]


def connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
    if not uid:
        print("ERROR: Odoo authentication failed")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def get_or_create_model(models, uid) -> int:
    existing = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.model", "search",
                                  [[["model", "=", "x_c21_building"]]])
    if existing:
        print(f"  Model x_c21_building already exists (id={existing[0]})")
        return existing[0]

    model_id = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.model", "create", [{
        "name": "大廈 Building",
        "model": "x_c21_building",
        "state": "manual",
    }])
    print(f"  Created model x_c21_building (id={model_id})")
    return model_id


def field_exists(models, uid, model_id: int, field_name: str) -> bool:
    return bool(models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY, "ir.model.fields", "search",
        [[["model_id", "=", model_id], ["name", "=", field_name]]],
    ))


def create_field(models, uid, model_id: int, vals: dict):
    name = vals["name"]
    if field_exists(models, uid, model_id, name):
        print(f"    Field {name} already exists, skipping")
        return
    fid = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.model.fields", "create",
                             [{**vals, "model_id": model_id, "state": "manual"}])
    print(f"    Created field {name} (id={fid})")


def setup_building_fields(models, uid, model_id: int):
    fields = [
        {"name": "x_name_en", "field_description": "English Name", "ttype": "char"},
        {"name": "x_address", "field_description": "Address 地址", "ttype": "char"},
        {
            "name": "x_district",
            "field_description": "District 地區",
            "ttype": "selection",
            "selection": str(DISTRICT_SELECTION),
        },
        {
            "name": "x_property_type",
            "field_description": "Property Type 物業類型",
            "ttype": "selection",
            "selection": str(PROPERTY_TYPE_SELECTION),
        },
        {"name": "x_als_geo_id", "field_description": "ALS Geo ID", "ttype": "char"},
        {"name": "x_lat", "field_description": "Latitude", "ttype": "float"},
        {"name": "x_lng", "field_description": "Longitude", "ttype": "float"},
        {"name": "x_needs_review", "field_description": "Needs Review", "ttype": "boolean"},
        {"name": "x_notes", "field_description": "Notes 備註", "ttype": "text"},
    ]
    for f in fields:
        create_field(models, uid, model_id, f)


def add_building_id_to_listing(models, uid, building_model_id: int):
    """Add x_building_id Many2one to existing x_c21_listing."""
    listing_model = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.model", "search",
                                       [[["model", "=", "x_c21_listing"]]])
    if not listing_model:
        print("  WARNING: x_c21_listing model not found")
        return
    listing_model_id = listing_model[0]

    if field_exists(models, uid, listing_model_id, "x_building_id"):
        print("  Field x_building_id on x_c21_listing already exists, skipping")
        return

    fid = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.model.fields", "create", [{
        "name": "x_building_id",
        "field_description": "Building 大廈",
        "ttype": "many2one",
        "relation": "x_c21_building",
        "model_id": listing_model_id,
        "state": "manual",
        "on_delete": "set null",
    }])
    print(f"  Added x_building_id to x_c21_listing (id={fid})")


def create_list_view(models, uid) -> int:
    existing = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.ui.view", "search",
                                  [[["model", "=", "x_c21_building"],
                                    ["type", "=", "list"],
                                    ["name", "=", "x_c21_building_list"]]],)
    if existing:
        print(f"  List view already exists (id={existing[0]})")
        return existing[0]

    arch = """<list string="大廈列表 Buildings">
  <field name="x_name"/>
  <field name="x_name_en"/>
  <field name="x_district"/>
  <field name="x_property_type"/>
  <field name="x_address"/>
  <field name="x_needs_review" optional="hide"/>
</list>"""

    vid = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.ui.view", "create", [{
        "name": "x_c21_building_list",
        "model": "x_c21_building",
        "type": "list",
        "arch": arch,
    }])
    print(f"  Created list view (id={vid})")
    return vid


def create_form_view(models, uid) -> int:
    existing = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.ui.view", "search",
                                  [[["model", "=", "x_c21_building"],
                                    ["type", "=", "form"],
                                    ["name", "=", "x_c21_building_form"]]],)
    if existing:
        print(f"  Form view already exists (id={existing[0]})")
        return existing[0]

    arch = """<form string="大廈 Building">
  <sheet>
    <div class="oe_title">
      <h1><field name="x_name" placeholder="大廈名稱 Building Name"/></h1>
      <h2><field name="x_name_en" placeholder="English Name"/></h2>
    </div>
    <group>
      <group string="Location 位置">
        <field name="x_district"/>
        <field name="x_property_type"/>
        <field name="x_address"/>
      </group>
      <group string="System">
        <field name="x_als_geo_id" readonly="1"/>
        <field name="x_needs_review"/>
      </group>
    </group>
    <notebook>
      <page string="單位 Units">
        <field name="x_listing_ids">
          <list>
            <field name="x_c21_floor_unit"/>
            <field name="x_c21_property_type"/>
            <field name="x_c21_size_sqft"/>
            <field name="x_c21_rent_net"/>
            <field name="x_c21_status"/>
            <field name="x_c21_contact_name"/>
            <field name="x_c21_date_received"/>
          </list>
        </field>
      </page>
      <page string="備註 Notes">
        <field name="x_notes"/>
      </page>
    </notebook>
  </sheet>
</form>"""

    vid = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.ui.view", "create", [{
        "name": "x_c21_building_form",
        "model": "x_c21_building",
        "type": "form",
        "arch": arch,
    }])
    print(f"  Created form view (id={vid})")
    return vid


def add_listing_count_field(models, uid, model_id: int):
    """Add computed x_listing_count field for the smart button."""
    if field_exists(models, uid, model_id, "x_listing_count"):
        print("  x_listing_count already exists, skipping")
        return
    # Odoo doesn't support computed fields via API in custom models easily.
    # The smart button will use a context filter instead — skip this field.
    print("  (Skipping computed count field — smart button uses context filter)")


def add_one2many_field(models, uid, model_id: int):
    """Add x_listing_ids One2many on x_c21_building → x_c21_listing."""
    if field_exists(models, uid, model_id, "x_listing_ids"):
        print("  x_listing_ids already exists, skipping")
        return

    fid = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.model.fields", "create", [{
        "name": "x_listing_ids",
        "field_description": "Units 單位",
        "ttype": "one2many",
        "relation": "x_c21_listing",
        "relation_field": "x_building_id",
        "model_id": model_id,
        "state": "manual",
    }])
    print(f"  Created x_listing_ids One2many (id={fid})")


def create_action_and_menu(models, uid):
    # Window action
    action_existing = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY, "ir.actions.act_window", "search",
        [[["res_model", "=", "x_c21_building"], ["name", "=", "大廈列表 Buildings"]]],
    )
    if action_existing:
        action_id = action_existing[0]
        print(f"  Action already exists (id={action_id})")
    else:
        action_id = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.actions.act_window", "create", [{
            "name": "大廈列表 Buildings",
            "res_model": "x_c21_building",
            "view_mode": "list,form",
            "target": "current",
        }])
        print(f"  Created window action (id={action_id})")

    # Find parent menu (C21 放盤管理)
    parent_menu = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY, "ir.ui.menu", "search",
        [[["name", "ilike", "放盤管理"]]],
    )
    parent_id = parent_menu[0] if parent_menu else False
    print(f"  Parent menu: {'id=' + str(parent_id) if parent_id else 'root (no parent found)'}")

    menu_existing = models.execute_kw(
        ODOO_DB, uid, ODOO_API_KEY, "ir.ui.menu", "search",
        [[["action", "=", f"ir.actions.act_window,{action_id}"]]],
    )
    if menu_existing:
        print(f"  Menu already exists (id={menu_existing[0]})")
    else:
        menu_id = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY, "ir.ui.menu", "create", [{
            "name": "大廈列表 Buildings",
            "parent_id": parent_id,
            "action": f"ir.actions.act_window,{action_id}",
            "sequence": 5,
        }])
        print(f"  Created menu item (id={menu_id})")


def main():
    if not ODOO_API_KEY:
        print("ERROR: ODOO_API_KEY not set in .env")
        sys.exit(1)

    print("Connecting to Odoo...")
    uid, models = connect()
    print(f"Authenticated as uid={uid}\n")

    print("1. Creating x_c21_building model...")
    model_id = get_or_create_model(models, uid)

    print("\n2. Adding fields to x_c21_building...")
    setup_building_fields(models, uid, model_id)

    print("\n3. Adding x_building_id Many2one to x_c21_listing...")
    add_building_id_to_listing(models, uid, model_id)

    print("\n4. Adding x_listing_ids One2many to x_c21_building...")
    add_one2many_field(models, uid, model_id)

    print("\n5. Creating list view...")
    create_list_view(models, uid)

    print("\n6. Creating form view (with Units tab)...")
    create_form_view(models, uid)

    print("\n7. Creating action + menu item...")
    create_action_and_menu(models, uid)

    print("\nDone. Open Odoo and refresh to see the new 大廈列表 Buildings menu.")


if __name__ == "__main__":
    main()
