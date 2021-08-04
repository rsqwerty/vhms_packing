# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from . import __version__ as app_version
from erpnext.stock.doctype.pick_list.pick_list import PickList
from erpnext.stock.doctype.item_price.item_price import ItemPrice

def pick_list_before_save(self):
    pass

# serial No Wise Item Price = IMPORTANT** (ADD "batch_no in live instance")
def check_duplicates_custom(self):
    conditions = """where item_code = %(item_code)s and price_list = %(price_list)s and name != %(name)s"""
    for field in ["uom","valid_from","valid_upto","packing_unit","customer","supplier","serial_no"]:
        if self.get(field):
            conditions += " and {0} = %({0})s ".format(field)
        else:
            conditions += "and (isnull({0}) or {0} = '')".format(field)

    price_list_rate = frappe.db.sql("""select price_list_rate from `tabItem Price`{conditions}""".format(conditions=conditions),self.as_dict(),)

    if price_list_rate:
        frappe.throw(_("Item Price appears multiple times based on Price List, Supplier/Customer, Currency, Item, Batch, Serial No, UOM, Qty, and Dates."), ItemPriceDuplicateItem,)


PickList.before_save = pick_list_before_save
#ItemPrice.check_duplicates = check_duplicates_custom

app_name = "vhms_packing"
app_title = "Vhms Packing"
app_publisher = "Fafadia Tech"
app_description = "Packing Development"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "manan@fafadiatech.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/vhms_packing/css/vhms_packing.css"
# app_include_js = "/assets/vhms_packing/js/vhms_packing.js"

# include js, css files in header of web template
# web_include_css = "/assets/vhms_packing/css/vhms_packing.css"
# web_include_js = "/assets/vhms_packing/js/vhms_packing.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "vhms_packing.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "vhms_packing.install.before_install"
# after_install = "vhms_packing.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "vhms_packing.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
#	}
# }

doc_events = {
    "Item":{
            "validate":"vhms_packing.validations.item_validate"
          },
    "Purchase Receipt":{
            "on_submit":"vhms_packing.validations.purchase_receipt_submit",
            "on_cancel":"vhms_packing.validations.pr_dn_se_cancel",
            "validate":"vhms_packing.validations.purchase_receipt_validate"
          },
    "Stock Entry":{
            "on_submit":"vhms_packing.validations.stock_entry_submit",
            "before_insert": "vhms_packing.validations.dn_se_before_insert",
            "on_cancel": "vhms_packing.validations.pr_dn_se_cancel",
            "validate": "vhms_packing.validations.stock_entry_validation",
          },
    "Delivery Note":{
            "on_submit":"vhms_packing.validations.delivery_note_submit",
            "before_insert":"vhms_packing.validations.dn_se_before_insert",
            "on_cancel":"vhms_packing.validations.pr_dn_se_cancel",
            "validate": "vhms_packing.validations.delivery_note_validation",
          },
    "Sales Invoice":{
            "on_submit":"vhms_packing.validations.sales_invoice_submit"
          },
    "Pick List":{
            "before_insert":"vhms_packing.validations.pick_list_validate",
            "on_submit": "vhms_packing.validations.pick_list_submit"
          },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"vhms_packing.tasks.all"
# 	],
# 	"daily": [
# 		"vhms_packing.tasks.daily"
# 	],
# 	"hourly": [
# 		"vhms_packing.tasks.hourly"
# 	],
# 	"weekly": [
# 		"vhms_packing.tasks.weekly"
# 	]
# 	"monthly": [
# 		"vhms_packing.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "vhms_packing.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "vhms_packing.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "vhms_packing.task.get_dashboard_data"
# }

fixtures = ["Custom Field"]
