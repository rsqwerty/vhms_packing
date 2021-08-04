import frappe
import json

from .api import create_packing_doctypes, update_packing_units, attach_xlsx
from frappe.utils.background_jobs import enqueue
#from vhms.api import attachment_barcode_sheet

def item_validate(doc, method):
    ipuid_selected = 0
    puid_selected = 0
    for child in doc.uoms:
        if child.generate_ipuid:
            ipuid_selected += 1

        if child.generate_puid:
            puid_selected += 1

    if ipuid_selected > 1:
        frappe.throw("IPUID Selected more than once")
        return False

    if puid_selected > 1:
        frappe.throw("PUID Selected more than once")
        return False

def push_mrp(item):
    for sr_no in item.serial_no.split("\n"):
        if not sr_no:
            continue
        frappe.db.set_value("Serial No", sr_no, "v_mrp",item.v_mrp)
        item_price_doc = frappe.get_doc({"doctype":"Item Price","item_code":item.item_code,"price_list":"Standard Selling","serial_no":sr_no,"price_list_rate":item.v_mrp})
        item_price_doc.save()
        frappe.db.commit()

def purchase_receipt_submit(doc, method):
    create_packing_doctypes(doc.name, doc.doctype)
    attach_xlsx(doc.name, doc.doctype)
    #for item in doc.items:
    #    push_mrp(item)

def push_oem_to_serial_no(item):
    has_oem_serial_no = frappe.get_value("Item",item.item_code, "has_oem_serial_no")
    if not has_oem_serial_no:
        return
    serial_nos = [sr_no for sr_no in item.serial_no.split("\n") if sr_no]
    oem_serial_nos = [sr_no for sr_no in item.oem_serial_no.split("\n") if sr_no]
    for sr_no,oem_sr_no in zip(serial_nos, oem_serial_nos):
        frappe.db.set_value("Serial No",sr_no,"oem_serial_no",oem_sr_no)
        frappe.db.commit()

def stock_entry_submit(doc, method):
    if doc.stock_entry_type == "Material Receipt":
        create_packing_doctypes(doc.name, doc.doctype)
        status = attach_xlsx(doc.name, doc.doctype)
        #for item in doc.items:
        #     push_mrp(item)
    elif doc.repack_same_item == "No":
        create_packing_doctypes(doc.name, doc.doctype)
        status = attach_xlsx(doc.name, doc.doctype)
    else:
        update_packing_units(doc)

def validate_comment(doc):
    if doc.doctype == "Pick List":
        items = doc.locations
    else:
        items = doc.items
    for item in items:
        serial_nos = item.serial_no.split("\n")
        if not item.suggested_serial_nos:
            continue

        for sr_no in item.suggested_serial_nos.split("\n"):
            if not sr_no or sr_no in serial_nos:
                continue
            if not item.comments:
                frappe.throw("Selected Serial Number does not match with Suggested Serial No Please Mention the reason in comments field")

def delivery_note_submit(doc, method):
    validate_comment(doc)
    update_packing_units(doc)
    attach_xlsx(doc.name, doc.doctype)
    #for item in doc.items:
    #    push_oem_to_serial_no(item)

def sales_invoice_submit(doc,method):
    pass
    #update_packing_units(doc)

def get_packing_qty(doc, item, unique_warehouses):
    puid_details = []
    ipuid_details = []
    valid_warehouse = []
    if not unique_warehouses:
        for warehouse in frappe.get_all("Warehouse", {"company":doc.company}):
            valid_warehouse.append(warehouse["name"])
    else:
        valid_warehouse = unique_warehouses.copy()
    puid_list = frappe.get_all("PUID", {"item_code":item.item_code,"warehouse":("in",(tuple(valid_warehouse)))},order_by='balance_stock_qty desc')
    ipuid_list = frappe.get_all("IPUID", {"item_code":item.item_code,"warehouse":("in",(tuple(valid_warehouse)))},order_by='balance_stock_qty desc')
    for puid in puid_list:
        balance_stock = frappe.get_value("PUID", puid["name"], "balance_stock_qty")
        if (item.stock_qty < balance_stock) or balance_stock == 0:
            continue
        else:
            puid_details.append({"puid":puid["name"],"qty":balance_stock,"warehouse":frappe.get_value("PUID",puid["name"],"warehouse")})
    for ipuid in ipuid_list:
        balance_stock = frappe.get_value("IPUID", ipuid["name"], "balance_stock_qty")
        if (item.stock_qty < balance_stock) or balance_stock == 0:
            continue
        else:
            ipuid_details.append({"ipuid":ipuid["name"],"qty":balance_stock,"warehouse":frappe.get_value("IPUID",ipuid["name"],"warehouse")})
    return puid_details, ipuid_details

def get_item_details(doc, item, unique_warehouses):
    refined_data = []
    invalid_ipuids = []
    reqd_qty = item.stock_qty
    puid_details, ipuid_details = get_packing_qty(doc, item, unique_warehouses)
    for item in puid_details:
        if reqd_qty < item["qty"] or 0 > item["qty"]:
            continue
        refined_data.append(item)
        reqd_qty -= item["qty"]
        for puid in frappe.get_all("Balance IPUID",{"parent":item["puid"]},"associated_ipuid"):
            invalid_ipuids.append(puid["associated_ipuid"])

    for ipuid_item in ipuid_details:
        if reqd_qty < ipuid_item["qty"] or ipuid_item["ipuid"] in invalid_ipuids or 0 > ipuid_item["qty"]:
            continue
        refined_data.append(ipuid_item)
        reqd_qty -= ipuid_item["qty"]
    return refined_data, reqd_qty

def get_packing_serial_nos(data):
    serial_nos = []
    selected_ipuid = []
    selected_puid = []
    for item in data:
        if "puid" in item:
            puid = item["puid"]
            selected_puid.append(puid)
            for associated_serial_nos in frappe.db.sql(f"SELECT associated_serial_no, associated_ipuid FROM `tabBalance IPUID` WHERE parent='{puid}'", as_dict=1):
                serial_nos += json.loads(associated_serial_nos["associated_serial_no"])
                selected_ipuid.append(associated_serial_nos["associated_ipuid"])

        if "ipuid" in item:
            ipuid = item["ipuid"]
            selected_ipuid.append(ipuid)
            for associated_serial_nos in frappe.db.sql(f"SELECT associated_serial_no FROM `tabBalance Serial No` WHERE parent='{ipuid}'"):
                serial_nos.append(associated_serial_nos[0])

    return serial_nos,selected_ipuid,selected_puid

def get_all_warehouses(parent_warehouses, all_children):
    immediate_children = frappe.get_all("Warehouse",{"parent_warehouse":["in",parent_warehouses]})
    if not immediate_children:
        return all_children
    all_children += immediate_children
    return get_all_warehouses([warehouse["name"] for warehouse in immediate_children], all_children)

def pick_list_validate(doc, method):
    if not doc.locations:
        return
    items = []
    locations = doc.locations.copy()
    doc.locations = []
    used_warehouses = []
    #for item in locations:
    #    if item.item_code in items:
    #        frappe.throw("Duplicate Items Present")
    #    else:
    #        items.append(item.item_code)
    for item in locations:
        unique_warehouses = []
        if item.warehouse:
            unique_warehouses.append(item.warehouse)
            used_warehouses.append(item.warehouse)
        elif doc.parent_warehouse:
            child_warehouses = frappe.get_all("Warehouse", {"name":["Descendants of", doc.parent_warehouse],"is_group":0})
            for warehouse in child_warehouses:
                if warehouse["name"] in used_warehouses:
                    continue
                unique_warehouses.append(warehouse["name"])
        refined_data, reqd_qty = get_item_details(doc,item,unique_warehouses)

        if not refined_data:
            doc.append("locations",item)
        for warehouse in unique_warehouses:
            warehouse_specific = []
            for data in refined_data:
                if data["warehouse"] != warehouse:
                    continue
                else:
                    warehouse_specific.append(data)
            if not warehouse_specific:
                continue
            serial_nos,ipuid,puid = get_packing_serial_nos(warehouse_specific)
            if reqd_qty != 0:
                remaining_serial_nos = frappe.db.sql(f"SELECT name FROM `tabSerial No` WHERE item_code='{item.item_code}' AND delivery_document_type is NULL AND warehouse='{warehouse}' and name not in {tuple(serial_nos)} LIMIT {int(reqd_qty)}", as_dict=1)
                for sr_no in remaining_serial_nos:
                    serial_nos.append(sr_no["name"])
                    reqd_qty -= 1

            doc.append("locations",{"item_code":item.item_code,"qty":item.qty,
                                    "uom":item.uom,"stock_qty":item.stock_qty,
                                    "warehouse":warehouse,"conversion_factor":item.conversion_factor,
                                    "suggested_serial_nos":"\n".join(serial_nos),"stock_uom":item.stock_uom,
                                    "suggested_ipuids":"\n".join(ipuid),
                                    "suggested_puids":"\n".join(puid),"batch_no":item.batch_no,
                                    "sales_order":item.sales_order,"sales_order_item":item.sales_order_item,
                                    "material_request":item.material_request,"material_request_item":item.material_request_item})
    #doc.save()
    #frappe.db.commit()

def dn_se_before_insert(doc, method):
    if not doc.pick_list:
        return

    for item in doc.items:
        warehouse = item.s_warehouse if doc.doctype == "Stock Entry" else item.warehouse
        units_details = frappe.get_value("Pick List Item",{"parent":doc.pick_list,"item_code":item.item_code, "warehouse":warehouse},["selected_puids","selected_ipuids","suggested_serial_nos","suggested_puids","suggested_ipuids","comments"], as_dict=1)
        item.selected_puids = units_details["selected_puids"] if units_details["selected_puids"] else ""
        item.selected_ipuids = units_details["selected_ipuids"] if units_details["selected_ipuids"] else ""
        item.suggested_serial_nos = units_details["suggested_serial_nos"] if units_details["suggested_serial_nos"] else ""
        item.suggested_puids = units_details["suggested_puids"] if units_details["suggested_puids"] else ""
        item.suggested_ipuids = units_details["suggested_ipuids"] if units_details["suggested_ipuids"] else ""

        if doc.doctype == "Delivery Note":
            item.comments = units_details["comments"] if units_details["comments"] else ""

def pick_list_submit(doc, method):
    validate_comment(doc)

def revert_packing_changes(sr_no):
    ipuid = frappe.get_value("Opening Serial No",{"associated_serial_no":sr_no},"parent")
    if not ipuid:
        return
    ipuid_doc = frappe.get_doc("IPUID", ipuid)
    ipuid_doc.append("balance_serial_no",{"associated_serial_no":sr_no})
    ipuid_doc.balance_stock_qty += 1
    ipuid_doc.save()
    frappe.db.commit()

    puid = frappe.get_value("Opening IPUID", {"associated_ipuid":ipuid},"parent")
    if not puid:
        return
    is_present = False
    puid_doc = frappe.get_doc("PUID", puid)
    for item in puid_doc.balance_ipuid:
        if item.associated_ipuid != ipuid:
            continue
        serial_nos = json.loads(item.associated_serial_no)
        serial_nos.append(sr_no)
        item.associated_serial_no = json.dumps(serial_nos)
        puid_doc.balance_stock_qty += 1
        puid_doc.save()
        frappe.db.commit()
        is_present = True
        break

    if not is_present:
        puid_doc.append("balance_ipuid",{"associated_serial_no":json.dumps([sr_no]),"associated_ipuid":ipuid})
        puid_doc.balance_stock_qty += 1
        puid_doc.balance_i_qty += 1
        puid_doc.save()
        frappe.db.commit()

def pr_dn_se_cancel(doc, method):
    for item in doc.items:
        if not item.serial_no:
            continue

        if doc.doctype == "Purchase Receipt":
            ipuids = item.ipuid.split("\n") if item.ipuid else []
            puids = item.puid.split("\n") if item.puid else []
        else:
            ipuids = item.selected_ipuids.split("\n") if item.selected_ipuids else []
            puids = item.selected_puids.split("\n") if item.selected_puids else []

        if (doc.doctype == "Purchase Receipt") or (doc.doctype == "Stock Entry" and doc.stock_entry_type == "Material Receipt"):
            for ipuid in ipuids:
                if not ipuid:
                    continue
                ipuid_doc = frappe.get_doc("IPUID", ipuid)
                ipuid_doc.delete()
                frappe.db.commit()
            for puid in puids:
                if not puid:
                    continue
                puid_doc = frappe.get_doc("PUID", puid)
                puid_doc.delete()
                frappe.db.commit()
        else:
            for sr_no in item.serial_no.split("\n"):
                if not sr_no:
                    continue
                frappe.db.sql("DELETE FROM `tabOut Details` WHERE out_voucher_id='{doc.doctype}' AND out_doctype='{doc.doctype}'")
                frappe.db.commit()
                revert_packing_changes(sr_no)

def oem_validation(doc):
    for item in doc.items:
        has_oem_serial_no = frappe.get_value("Item",item.item_code, "has_oem_serial_no")
        if not has_oem_serial_no:
            continue
        if not item.oem_serial_no:
            frappe.throw(f"Please Add the oem serial no for item {item.item_code}")
        serial_nos = [sr_no for sr_no in item.serial_no.split("\n") if sr_no]
        oem_serial_nos = [sr_no for sr_no in item.oem_serial_no.split("\n") if sr_no]
        if len(serial_nos) == len(oem_serial_nos):
            continue
        else:
            frappe.throw(f"Please Match the oem serial nos with serial nos for item {item.item_code}")

def delivery_note_validation(doc, method):
    pass
    #oem_validation(doc)
    #validate_item_price(doc)

def stock_entry_validation(doc, method):
    if doc.stock_entry_type == "Repack" and doc.repack_same_item not in ["Yes", "No"]:
        frappe.throw("Please Mention yes or no in Repack Same Item")
    if doc.stock_entry_type != "Repack" and doc.repack_same_item in ["Yes", "No"]:
        frappe.throw("Please remove values in Repack Same Item field")
    if doc.stock_entry_type != "Material Receipt":
        pass
        #oem_validation(doc)
        #validate_item_price(doc)

def validate_item_price(doc):
    for item in doc.items:
        item_prices = frappe.get_all("Item Price", {"serial_no":['in',item.serial_no.split("\n")]}, ["price_list_rate","serial_no"])
        values = {}
        for price in item_prices:
            if price["price_list_rate"] in values:
                sr_nos = values[price["price_list_rate"]]
                sr_nos.append(price["serial_no"])
                values[price["price_list_rate"]] = sr_nos
            else:
                values[price["price_list_rate"]] = [price["serial_no"]]

        if len(values) > 1:
            frappe.throw(f"Please Make {len(values)} row for item = {item.item_code} as price differs for serial no")

        if values.keys():
            item.rate = list(values.keys())[0] * ((100-item.discount_percentage)/100)

def validate_uom_association(item):
    value = frappe.get_value("UOM Conversion Detail",{"parent":item.item_code,"uom":item.uom},"name")
    if not value:
        frappe.throw(f"Please Add Valid UOM for item - {item.item_code}")

def purchase_receipt_validate(doc, method):
    for item in doc.items:
        validate_uom_association(item)

def stock_entry_type(doc, method):
    if doc.stock_entry_type != "Material Receipt":
        return

    for item in doc.items:
        validate_uom_association(item)
