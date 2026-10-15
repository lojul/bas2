"""One-time setup: build the 放盤管理 → 文件上傳 upload page in Odoo, Studio-style.

Creates exactly what Odoo Studio would (all editable/exportable in Studio
afterwards — each record gets a studio_customization xmlid):
  - model x_c21_doc_upload (with chatter) + x_studio_* fields
  - access for internal users, default status 待處理
  - list + form views (status bar, 重新處理 button, chatter)
  - window action + menu 放盤管理 → 文件上傳 Upload
  - webhook server action for the 重新處理 button
  - automation rule "On create" → webhook to the doc-pipeline App Service

The webhook URL carries ODOO_UPLOAD_WEBHOOK_TOKEN (from .env) — the same value
must be set as an App Service app setting. Field/model names here are the
defaults src/utils/odoo_upload.py expects.

Idempotent: re-running skips anything that already exists.

    cd langgraph && source .venv/bin/activate
    python scripts/setup_odoo_doc_upload.py              # automation rule created INACTIVE
    python scripts/setup_odoo_doc_upload.py --activate   # switch the rule on (after deploy)
"""

import argparse
import os
import sys
import uuid
import xmlrpc.client

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

ODOO_URL = "https://c21net.odoo.com"
ODOO_DB = "c21net"
ODOO_USERNAME = "admin@c21net.com"
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")
WEBHOOK_TOKEN = os.environ.get("ODOO_UPLOAD_WEBHOOK_TOKEN", "")
API_HOST = "https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net"

MODEL = "x_c21_doc_upload"
PARENT_MENU = "C21 放盤管理"
RULE_NAME = "文件上傳：新上傳自動處理"
BUTTON_ACTION_NAME = "文件上傳：重新處理"

DOC_TYPES = [
    ("auto", "自動 Auto"), ("listing", "放盤 Listing"), ("listing_list", "放盤表 Listing List"),
    ("pitching_deck", "樓書 Pitching Deck"), ("news", "新聞 News"), ("contact", "名片 Contact"),
]
STATUSES = [("pending", "待處理"), ("processing", "處理中"), ("done", "完成"), ("error", "失敗")]

FIELDS = [
    {"name": "x_studio_file", "field_description": "檔案 File", "ttype": "binary", "copied": False},
    {"name": "x_studio_file_filename", "field_description": "檔案名稱 File Name", "ttype": "char"},
    {"name": "x_studio_doc_type", "field_description": "文件類型 Type", "ttype": "selection",
     "selection_ids": DOC_TYPES},
    {"name": "x_studio_allow_duplicate", "field_description": "允許重複 Allow Duplicate", "ttype": "boolean"},
    {"name": "x_studio_status", "field_description": "狀態 Status", "ttype": "selection",
     "selection_ids": STATUSES, "tracking": 1, "copied": False},
    {"name": "x_studio_result", "field_description": "處理結果 Result", "ttype": "text", "copied": False},
    {"name": "x_studio_listing_ids", "field_description": "相關放盤 Listings", "ttype": "many2many",
     "relation": "x_c21_listing", "relation_table": "x_c21_doc_upload_x_c21_listing_rel",
     "column1": "x_c21_doc_upload_id", "column2": "x_c21_listing_id", "copied": False},
]

LIST_ARCH = f"""<list string="文件上傳 Uploads" default_order="create_date desc">
  <field name="create_date" string="上傳時間"/>
  <field name="x_name"/>
  <field name="x_studio_doc_type"/>
  <field name="x_studio_status" widget="badge"
         decoration-success="x_studio_status == 'done'" decoration-danger="x_studio_status == 'error'"
         decoration-info="x_studio_status == 'processing'"/>
  <field name="create_uid" string="上傳者" widget="many2one_avatar_user"/>
</list>"""

FORM_ARCH = """<form string="文件上傳 Upload">
  <header>
    <button name="{button_action_id}" type="action" string="重新處理 Reprocess"
            class="btn-secondary" invisible="not id or x_studio_status == 'processing'"/>
    <field name="x_studio_status" widget="statusbar" readonly="1"/>
  </header>
  <sheet>
    <div class="oe_title">
      <h1><field name="x_name" placeholder="說明（選填，留空則用檔案名稱）"/></h1>
    </div>
    <group>
      <group>
        <field name="x_studio_file" filename="x_studio_file_filename" required="1"/>
        <field name="x_studio_file_filename" invisible="1"/>
        <field name="x_studio_doc_type"/>
      </group>
      <group>
        <field name="x_studio_allow_duplicate"
               help="只適用於新聞：已有相同文章時仍然建立"/>
        <field name="create_uid" string="上傳者" readonly="1"/>
        <field name="create_date" string="上傳時間" readonly="1"/>
      </group>
    </group>
    <group string="處理結果 Result" invisible="not x_studio_result and not x_studio_listing_ids">
      <field name="x_studio_result" nolabel="1" colspan="2" readonly="1"/>
      <field name="x_studio_listing_ids" colspan="2" readonly="1" widget="many2many_tags"/>
    </group>
  </sheet>
  <chatter/>
</form>"""


class Odoo:
    def __init__(self) -> None:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        self.uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
        if not self.uid:
            sys.exit("ERROR: Odoo authentication failed")
        self.models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    def __call__(self, model: str, method: str, *args, **kwargs):
        return self.models.execute_kw(ODOO_DB, self.uid, ODOO_API_KEY, model, method, list(args), kwargs)

    def find(self, model: str, domain: list) -> int | None:
        ids = self(model, "search", domain, limit=1)
        return ids[0] if ids else None

    def ensure(self, model: str, domain: list, vals: dict, label: str) -> int:
        """Create the record unless one matching domain exists; tag new ones like Studio does."""
        rid = self.find(model, domain)
        if rid:
            print(f"  {label}: exists (id={rid})")
            return rid
        rid = self(model, "create", [vals])[0]
        self("ir.model.data", "create", [{
            "module": "studio_customization",
            "name": f"odoo_studio_{MODEL}_{uuid.uuid4()}",
            "model": model, "res_id": rid, "studio": True, "noupdate": True,
        }])
        print(f"  {label}: created (id={rid})")
        return rid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--activate", action="store_true", help="switch the automation rule on")
    args = ap.parse_args()
    if not ODOO_API_KEY:
        sys.exit("ERROR: ODOO_API_KEY not set in .env")
    if not WEBHOOK_TOKEN:
        sys.exit("ERROR: ODOO_UPLOAD_WEBHOOK_TOKEN not set in .env")

    odoo = Odoo()
    webhook_url = f"{API_HOST}/api/odoo/upload?token={WEBHOOK_TOKEN}"

    print("1. Model")
    model_id = odoo.ensure("ir.model", [["model", "=", MODEL]], {
        "name": "文件上傳 Document Upload", "model": MODEL, "state": "manual",
        "is_mail_thread": True, "is_mail_activity": True, "order": "create_date desc",
    }, MODEL)

    print("2. Fields")
    for f in FIELDS:
        vals = {**f, "model_id": model_id, "state": "manual"}
        if "selection_ids" in vals:
            vals["selection_ids"] = [(0, 0, {"value": v, "name": n, "sequence": i})
                                     for i, (v, n) in enumerate(vals["selection_ids"])]
        odoo.ensure("ir.model.fields", [["model_id", "=", model_id], ["name", "=", f["name"]]],
                    vals, f["name"])

    print("3. Access + default status")
    group_user = odoo("ir.model.data", "search_read",
                      [["module", "=", "base"], ["name", "=", "group_user"]], fields=["res_id"])[0]["res_id"]
    odoo.ensure("ir.model.access", [["model_id", "=", model_id], ["group_id", "=", group_user]], {
        "name": f"{MODEL}_group_user", "model_id": model_id, "group_id": group_user,
        "perm_read": True, "perm_write": True, "perm_create": True, "perm_unlink": True,
    }, "access (internal users)")
    status_field = odoo.find("ir.model.fields", [["model_id", "=", model_id], ["name", "=", "x_studio_status"]])
    odoo.ensure("ir.default", [["field_id", "=", status_field], ["user_id", "=", False], ["company_id", "=", False]],
                {"field_id": status_field, "json_value": '"pending"'}, "default status 待處理")

    print("4. Button webhook action")
    button_action = odoo.ensure("ir.actions.server", [["name", "=", BUTTON_ACTION_NAME], ["model_id", "=", model_id]], {
        "name": BUTTON_ACTION_NAME, "model_id": model_id, "state": "webhook", "webhook_url": webhook_url,
    }, BUTTON_ACTION_NAME)

    print("5. Views")
    odoo.ensure("ir.ui.view", [["model", "=", MODEL], ["type", "=", "list"], ["inherit_id", "=", False]], {
        "name": f"{MODEL}_list", "model": MODEL, "type": "list", "arch": LIST_ARCH,
    }, "list view")
    odoo.ensure("ir.ui.view", [["model", "=", MODEL], ["type", "=", "form"], ["inherit_id", "=", False]], {
        "name": f"{MODEL}_form", "model": MODEL, "type": "form",
        "arch": FORM_ARCH.format(button_action_id=button_action),
    }, "form view")

    print("6. Action + menu")
    window_action = odoo.ensure("ir.actions.act_window", [["res_model", "=", MODEL]], {
        "name": "文件上傳 Upload", "res_model": MODEL, "view_mode": "list,form",
        "help": "<p class='o_view_nocontent_smiling_face'>上傳放盤文件</p>"
                "<p>上傳後會自動以 WhatsApp / Slack 相同流程處理，結果寫入放盤列表。</p>",
    }, "window action")
    parent = odoo.find("ir.ui.menu", [["name", "=", PARENT_MENU], ["parent_id", "=", False]])
    if not parent:
        sys.exit(f"ERROR: menu '{PARENT_MENU}' not found")
    odoo.ensure("ir.ui.menu", [["action", "=", f"ir.actions.act_window,{window_action}"]], {
        "name": "文件上傳 Upload", "parent_id": parent, "sequence": 1,
        "action": f"ir.actions.act_window,{window_action}",
    }, "menu 放盤管理 → 文件上傳")

    print("7. Automation rule (On create → webhook)")
    rule = odoo.ensure("base.automation", [["name", "=", RULE_NAME], ["active", "in", [True, False]]], {
        "name": RULE_NAME, "model_id": model_id, "trigger": "on_create", "active": False,
    }, RULE_NAME)
    odoo.ensure("ir.actions.server", [["base_automation_id", "=", rule]], {
        "name": "送出處理 Send to pipeline", "model_id": model_id, "state": "webhook",
        "webhook_url": webhook_url, "base_automation_id": rule, "usage": "base_automation",
    }, "rule webhook action")

    # Keep both webhook URLs in step with the current token
    for aid in odoo("ir.actions.server", "search", [["model_id", "=", model_id], ["state", "=", "webhook"]]):
        odoo("ir.actions.server", "write", [aid], {"webhook_url": webhook_url})

    if args.activate:
        odoo("base.automation", "write", [rule], {"active": True})
    active = odoo("base.automation", "read", [rule], fields=["active"])[0]["active"]
    print(f"\nDone. Automation rule is {'ACTIVE' if active else 'INACTIVE — run with --activate after deploy'}.")


if __name__ == "__main__":
    main()
