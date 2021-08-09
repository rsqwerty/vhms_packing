import os
import frappe
import json
import shutil
import datetime
from io import BytesIO

import PIL
import pdfkit
import barcode
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from barcode.writer import ImageWriter
from PyPDF2 import PdfFileReader, PdfFileWriter

def get_uom_details(item_code, uom):
    values = frappe.db.sql(f"SELECT generate_ipuid,generate_puid  FROM `tabUOM Conversion Detail` WHERE uom='{uom}' AND parent=%s",item_code,as_dict=1)
    return values[0]["generate_puid"], values[0]["generate_ipuid"]

def create_ipuid(item, ipuid_nos, ipuid_conv, doctype):
    serial_index = 0
    ipuid_created = []
    names = ""
    serial_nos = item.serial_no.split("\n")
    for no in range(int(ipuid_nos)):
        individual_list = []
        serial_nos_in_ipuid = []
        for index in range(int(ipuid_conv)):
            associated_serial = {}
            if serial_index < len(serial_nos):
                associated_serial["associated_serial_no"] = serial_nos[serial_index]
                serial_nos_in_ipuid.append(serial_nos[serial_index])
                individual_list.append(associated_serial)
                serial_index += 1
        if doctype == "Stock Entry":
            warehouse = item.t_warehouse
        else:
            warehouse = item.warehouse
        doc = frappe.get_doc({
                             "doctype":"IPUID",
                             "naming_series":frappe.get_value("UOM Conversion Detail", {"parent":item.item_code,"generate_ipuid":1},"ipuid_series"),
                             "item_code":item.item_code,
                             "reference_id":item.parent,
                             "reference_doctype":doctype,
                             "warehouse": warehouse,
                             "associated_serial_no": individual_list,
                             "opening_stock_qty":len(individual_list),
                             "balance_serial_no": individual_list,
                             "balance_stock_qty":len(individual_list),
                             "opening_stock_uom":item.stock_uom,
                             "balance_stock_uom":item.stock_uom,
                             })
        doc.insert()
        frappe.db.commit()
        ipuid_created.append({"doc":doc.name,"serial_nos":serial_nos_in_ipuid})
        names += doc.name + " "
    frappe.msgprint(f"Ipuids created : {names}")
    return ipuid_created

def get_no_of_ipuid(item):
    ipuid_conv = int(frappe.get_value("UOM Conversion Detail", {"parent":item.item_code, "generate_ipuid":1},"conversion_factor"))
    return (int(item.conversion_factor)/ipuid_conv) * item.qty, ipuid_conv

def create_puid(item, doctype):
    ipuid_index = 0
    puid_created = ""
    ipuid_nos, ipuid_conv = get_no_of_ipuid(item)
    created_ipuid_list = create_ipuid(item, ipuid_nos, ipuid_conv, doctype)
    for no in range(int(item.qty)):
        opening_ipuid = []
        for i in range(int(item.conversion_factor/ipuid_conv)):
            if ipuid_index < len(created_ipuid_list):
                individual_ipuid = {}
                individual_ipuid["associated_ipuid"] = created_ipuid_list[ipuid_index]["doc"]
                individual_ipuid["associated_serial_no"] = json.dumps(created_ipuid_list[ipuid_index]["serial_nos"])
                opening_ipuid.append(individual_ipuid)
                ipuid_index += 1
        if doctype == "Stock Entry":
            warehouse = item.t_warehouse
        else:
            warehouse = item.warehouse
        doc = frappe.get_doc({
                             "doctype":"PUID",
                             "naming_series":frappe.get_value("UOM Conversion Detail", {"parent":item.item_code,"generate_puid":1},"puid_series"),
                             "item_code":item.item_code,
                             "reference_id":item.parent,
                             "reference_doctype":doctype,
                             "warehouse": warehouse,
                             "opening_ipuid": opening_ipuid,
                             "opening_i_qty": len(opening_ipuid),
                             "balance_i_qty": len(opening_ipuid),
                             "opening_stock_qty": int(item.conversion_factor),
                             "balance_ipuid": opening_ipuid,
                             "balance_stock_qty": int(item.conversion_factor),
                             "opening_i_uom":frappe.get_value("UOM Conversion Detail", {"parent":item.item_code, "generate_ipuid":1},"uom"),
                             "opening_stock_uom":item.stock_uom,
                             "balance_i_uom":frappe.get_value("UOM Conversion Detail", {"parent":item.item_code, "generate_ipuid":1},"uom"),
                             "balance_stock_uom":item.stock_uom,
                             })
        doc.insert()
        frappe.db.commit()
        puid_created += doc.name + " "
    frappe.msgprint(f"PUIDs - {puid_created}")

def get_packing_details(doctype,id,item_code):
    ipuids_json = ""
    puids_json = ""
    ipuids = frappe.get_all("IPUID", {"item_code":item_code, "reference_doctype":doctype,"reference_id":id})
    for ipuid in ipuids:
       ipuids_json += ipuid["name"] + "\n"
    puids = frappe.get_all("PUID", {"item_code":item_code, "reference_doctype":doctype,"reference_id":id})
    for puid in puids:
       puids_json += puid["name"] + "\n"
    return ipuids_json, puids_json

def update_docs(doc):
    for item in doc.items:
        ipuid, puid = get_packing_details(doc.doctype, doc.name, item.item_code)
        item.puid = puid
        item.ipuid = ipuid
        sle_name = frappe.get_value("Stock Ledger Entry",{"voucher_type":doc.doctype,"voucher_no":doc.name,"voucher_detail_no":item.name,"item_code":item.item_code},"name")
        sle_doc = frappe.get_doc("Stock Ledger Entry", sle_name)
        sle_doc.puid = puid
        sle_doc.ipuid = ipuid
        sle_doc.save()
    doc.save()
    frappe.db.commit()

    #attach excel Sheet

def create_packing_doctypes(name, doctype):
    doc = frappe.get_doc(doctype, name)
    for item in doc.items:
        if not item.serial_no:
            continue
        is_puid, is_ipuid = get_uom_details(item.item_code, item.uom)
        print(is_puid, is_ipuid)
        if is_puid:
            create_puid(item, doctype)
        elif is_ipuid:
            create_ipuid(item, item.qty, item.conversion_factor, doctype)
        else:
            continue

    update_docs(doc)

def get_puid_details(puid_doc):
    ipuids = ""
    sr_nos = ""
    for item in puid_doc.balance_ipuid:
        ipuids += item.associated_ipuid + "\n"
        sr_nos += "\n".join(json.loads(item.associated_serial_no))
    return ipuids, sr_nos

def update_partial_packing_units(ipuids, serial_nos, doc):
    unassociated_serial_nos = serial_nos.copy()
    values = []
    if ipuids:
        ipuids.append("")
        values = frappe.db.sql(f"SELECT associated_serial_no FROM `tabBalance Serial No` WHERE parent in {tuple(ipuids)}", as_dict=1)
    for value in values:
        if value["associated_serial_no"] in serial_nos:
            unassociated_serial_nos.remove(value["associated_serial_no"])
    ipuids_association = {}
    for sr_no in unassociated_serial_nos:
        ipuid = frappe.get_value("Balance Serial No",{"associated_serial_no":sr_no},"parent")
        if not ipuid:
            continue

        if ipuid not in ipuids_association:
            ipuids_association[ipuid] = [sr_no]
        else:
            ipuids_association[ipuid].append(sr_no)

    for k,v in ipuids_association.items():
        ipuid_doc = frappe.get_doc("IPUID",k)
        ipuid_table = ipuid_doc.balance_serial_no.copy()
        ipuid_doc.balance_serial_no = []
        for index, associated_row in enumerate(ipuid_table):
            if associated_row.associated_serial_no in v:
                continue

            ipuid_doc.append("balance_serial_no", associated_row.__dict__)
        ipuid_doc.balance_stock_qty -= len(v)
        ipuid_doc.append("out_details_table",{"out_doctype":doc.doctype,
                                              "out_voucher_id":doc.name,
                                              "out_date":doc.posting_date,
                                              "out_serial_no":"\n".join(v)})
        ipuid_doc.save()
        frappe.db.commit()
        puid = frappe.get_value("Balance IPUID", {"associated_ipuid":k},"parent")
        if not puid:
            continue

        puid_doc = frappe.get_doc("PUID",puid)
        puid_table = puid_doc.balance_ipuid
        puid_doc.balance_ipuid = []
        for index,associated_row in enumerate(puid_doc.balance_ipuid.copy()):
            if associated_row.associated_ipuid != k:
                puid_doc.append(balance_ipuid, associated_row.__dict__)
            puid_sr_nos = json.loads(associated_row.associated_serial_no)
            for sr_no in v:
                if sr_no not in puid_sr_nos.copy():
                    continue

                puid_sr_nos.remove(sr_no)
            if len(puid_sr_nos) == 0:
                puid_doc.balance_i_qty = puid_doc.balance_i_qty -1
            else:
                puid_doc.append("balance_ipuid",{"associated_ipuid":k,"associated_serial_no":json.dumps(puid_sr_nos)})
            puid_doc.balance_stock_qty = puid_doc.balance_stock_qty - len(v)
            puid_doc.append("out_details_table",{"out_doctype":doc.doctype,
                                                 "out_voucher_id":doc.name,
                                                 "out_date":doc.posting_date,
                                                 "packing_doctype":"IPUID",
                                                 "out_packing_id":k,
                                                 "out_serial_no":"\n".join(v)})
            puid_doc.save()
            frappe.db.commit()

def update_packing_units(doc):
    for item in doc.items:
        if not item.serial_no:
            continue
        sle_names = frappe.get_all("Stock Ledger Entry",{"voucher_detail_no":item.name,"voucher_no":doc.name},"name")
        for sle_name in sle_names:
            sle_doc = frappe.get_doc("Stock Ledger Entry", sle_name)
            sle_doc.ipuid = item.selected_ipuids
            sle_doc.puid = item.selected_puids
            sle_doc.save()
            frappe.db.commit()
        ipuids = item.selected_ipuids.split("\n") if item.selected_ipuids else []
        puids = item.selected_puids.split("\n") if item.selected_puids else []
        sr_nos = item.serial_no.split("\n") if item.serial_no else []
        for puid in puids:
            if puid:
                puid_doc = frappe.get_doc("PUID", puid)
                puid_doc.reference_doctype = doc.doctype
                puid_doc.reference_id = doc.name
                puid_doc.warehouse = item.t_warehouse if doc.doctype == "Stock Entry" else item.warehouse
                if doc.doctype == "Stock Entry" and doc.stock_entry_type == "Material Transfer":
                    pass
                else:
                    puid_doc.balance_i_qty = 0
                    puid_doc.balance_stock_qty = 0
                associated_ipuids, associated_serial_nos = get_puid_details(puid_doc)
                puid_doc.append("out_details_table",{"out_doctype":doc.doctype,
                                                     "out_voucher_id":doc.name,
                                                     "out_date":doc.posting_date,
                                                     "packing_doctype":"IPUID",
                                                     "out_packing_id":associated_ipuids,
                                                     "out_serial_no":associated_serial_nos})
                if doc.doctype == "Stock Entry" and doc.stock_entry_type == "Material Transfer":
                    pass
                else:
                    puid_doc.balance_ipuid =  []
                puid_doc.save()
                frappe.db.commit()
        partial_puids = frappe.get_all("Balance IPUID",{"associated_ipuid":["in",ipuids],"parent":["not in",puids]}, "distinct parent")

        for puid in partial_puids:
            associated_ipuids, associated_serial_nos = "",""
            serial_count = 0
            ipuid_count = 0
            puid_doc = frappe.get_doc("PUID", puid["parent"])
            balance = puid_doc.balance_ipuid.copy()
            puid_doc.balance_ipuid = []
            for index, row in enumerate(balance):
                if row.associated_ipuid not in ipuids:
                    puid_doc.append("balance_ipuid", row.__dict__)
                    continue

                associated_ipuids += row.associated_ipuid + "\n"
                associated_serial_nos += "\n".join(json.loads(row.associated_serial_no)) + "\n"
                serial_count += len(json.loads(row.associated_serial_no))
                ipuid_count += 1
            puid_doc.append("out_details_table",{"out_doctype":doc.doctype,
                                                 "out_voucher_id":doc.name,
                                                 "out_date":doc.posting_date,
                                                 "packing_doctype":"IPUID",
                                                 "out_packing_id":associated_ipuids,
                                                 "out_serial_no":associated_serial_nos})
            puid_doc.balance_i_qty -= ipuid_count
            puid_doc.balance_stock_qty = puid_doc.balance_stock_qty - serial_count
            puid_doc.save()
            frappe.db.commit()
        for ipuid in ipuids:
            if ipuid:
                ipuid_doc = frappe.get_doc("IPUID", ipuid)
                ipuid_doc.reference_doctype = doc.doctype
                ipuid_doc.reference_id = doc.name
                ipuid_doc.warehouse = item.t_warehouse if doc.doctype == "Stock Entry" else item.warehouse
                if doc.doctype == "Stock Entry" and doc.stock_entry_type == "Material Transfer":
                    pass
                else:
                    ipuid_doc.balance_stock_qty = 0
                ipuid_doc.append("out_details_table",{"out_doctype":doc.doctype,
                                             "out_voucher_id":doc.name,
                                             "out_date":doc.posting_date,
                                             "out_serial_no":"\n".join([serial_no.associated_serial_no for serial_no in ipuid_doc.balance_serial_no])})
                if doc.doctype == "Stock Entry" and doc.stock_entry_type == "Material Transfer":
                    pass
                else:
                    ipuid_doc.balance_serial_no = []
                ipuid_doc.save()
                frappe.db.commit()
        update_partial_packing_units(ipuids,item.serial_no.split("\n"), doc)
        #Implement Later
        #if item.selected_ipuids:
        #    serial_nos = get_sr_from_puids(item.selected_ipuids)

def is_all_ipuids(puid, ipuids):
    associated_ipuids = frappe.get_all("Balance IPUID",{"parent":puid},"associated_ipuid")
    for item in associated_ipuids:
        if item["associated_ipuid"] not in ipuids:
            return False
    return True

@frappe.whitelist()
def ipuids_change(child):
    child = json.loads(child)
    if not frappe.get_value("Item",child["item_code"],"has_serial_no"):
        return
    updated_sr_no = set(child["serial_no"].split("\n")) if "serial_no" in child else set()
    updated_puids = set(child["selected_puids"].split("\n")) if "selected_puids" in child else set()
    before_saved_ipuids = frappe.get_value(child["doctype"], child["name"],"selected_ipuids") or ""
    is_added = True if len(child["selected_ipuids"]) >= len(before_saved_ipuids) else False
    if is_added:
        for ipuid in child["selected_ipuids"].split("\n"):
            if ipuid in before_saved_ipuids.split("\n"):
                continue
            associated_serial_nos = frappe.get_all("Balance Serial No",{"parent":ipuid},["associated_serial_no"])
            for sr_no in associated_serial_nos:
                updated_sr_no.add(sr_no["associated_serial_no"])
            associated_puid = frappe.get_value("Balance IPUID",{"associated_ipuid":ipuid},"parent")
            if not associated_puid or (associated_puid in updated_puids):
                continue

            if is_all_ipuids(associated_puid, child["selected_ipuids"].split("\n")):
                updated_puids.add(associated_puid)
    else:
        for ipuid in before_saved_ipuids.split("\n"):
            if ipuid in child["selected_ipuids"].split("\n"):
                continue
            associated_serial_nos = frappe.get_all("Balance Serial No",{"parent":ipuid},["associated_serial_no"])
            for sr_no in associated_serial_nos:
                updated_sr_no.remove(sr_no["associated_serial_no"])
            associated_puid = frappe.get_value("Balance IPUID",{"associated_ipuid":ipuid},"parent")
            if associated_puid and (associated_puid in updated_puids):
                updated_puids.remove(associated_puid)

    save_docs(child, updated_sr_no, child["selected_ipuids"].split("\n"), updated_puids)

@frappe.whitelist()
def accept_values(doc_name,child_name):
    doc = frappe.get_doc("Pick List", doc_name)
    for item in doc.locations:
        if item.name == child_name:
            item.picked_qty = len(item.suggested_serial_nos.split("\n"))
            item.puid_qty = len(item.suggested_puids.split("\n"))
            item.ipuid_qty = len(item.suggested_ipuids.split("\n"))
            item.selected_puids = item.suggested_puids
            item.selected_ipuids = item.suggested_ipuids
            item.serial_no = item.suggested_serial_nos
    doc.save()
    frappe.db.commit()

@frappe.whitelist()
def serial_no_change(child):
    child = json.loads(child)
    if not frappe.get_value("Item",child["item_code"],"has_serial_no"):
        return
    ipuids = []
    puids = []
    serial_nos = child["serial_no"].split("\n") if "serial_no" in child else []
    associated_ipuids = frappe.get_all("Balance Serial No", {"associated_serial_no":["in",serial_nos]}, "distinct parent")
    for index, ipuid in enumerate(associated_ipuids):
        ipuids.append(ipuid["parent"])
        associated_serial_no = frappe.get_all("Balance Serial No", {"parent":ipuid["parent"]},"associated_serial_no")
        for sr in associated_serial_no:
            if sr["associated_serial_no"] not in serial_nos:
                ipuids.remove(ipuid["parent"])
                break

    associated_puids = frappe.get_all("Balance IPUID",{"associated_ipuid":["in",ipuids]},"distinct parent")
    for index, puid in enumerate(associated_puids):
        puids.append(puid["parent"])
        associated_ipuids = frappe.get_all("Balance IPUID", {"parent": puid["parent"]},"associated_ipuid")
        for row in associated_ipuids:
            if row["associated_ipuid"] not in ipuids:
                puids.remove(puid["parent"])
                break

    save_docs(child, serial_nos, ipuids, puids)

@frappe.whitelist()
def puids_change(child):
    child = json.loads(child)
    if not frappe.get_value("Item",child["item_code"],"has_serial_no"):
        return
    updated_sr_no = set(child["serial_no"].split("\n")) if "serial_no" in child else set()
    updated_ipuids = set(child["selected_ipuids"].split("\n")) if "selected_ipuids" in child else set()
    before_saved_puids = frappe.get_value(child["doctype"], child["name"],"selected_puids") or ""
    is_added = True if len(child["selected_puids"]) >= len(before_saved_puids) else False
    if is_added:
        for puid in child["selected_puids"].split("\n"):
            if puid in before_saved_puids.split("\n"):
                continue
            associated_serial_nos = frappe.get_all("Balance IPUID",{"parent":puid},["associated_serial_no", "associated_ipuid"])
            for sr_no in associated_serial_nos:
                updated_sr_no.update(json.loads(sr_no["associated_serial_no"]))
                updated_ipuids.add(sr_no["associated_ipuid"])
    else:
        for puid in before_saved_puids.split("\n"):
            if puid in child["selected_puids"].split("\n"):
                continue
            associated_serial_nos = frappe.get_all("Balance IPUID",{"parent":puid},["associated_serial_no","associated_ipuid"])
            for sr_no in associated_serial_nos:
                updated_sr_no -= set(json.loads(sr_no["associated_serial_no"]))
                updated_ipuids.remove(sr_no["associated_ipuid"])

    save_docs(child, updated_sr_no, updated_ipuids, child["selected_puids"].split("\n"))


def save_docs(child,updated_sr_no,updated_ipuids,updated_puids):
    doc = frappe.get_doc(child["doctype"].replace("Item","").replace("Detail","").strip(), child["parent"])
    updated_sr_no = list(filter(len, updated_sr_no))
    updated_ipuids = list(filter(len, updated_ipuids))
    updated_puids = list(filter(len, updated_puids))

    if doc.doctype == "Pick List":
        for item in doc.locations:
            if item.name != child["name"]:
                continue

            item.serial_no = "\n".join(updated_sr_no)
            item.selected_ipuids = "\n".join(updated_ipuids)
            item.selected_puids = "\n".join(updated_puids)
            item.picked_qty = len(updated_sr_no)
            item.ipuid_qty = len(updated_ipuids)
            item.puid_qty = len(updated_puids)
            break
    else:
        for item in doc.items:
            if item.name != child["name"]:
                continue

            item.serial_no = "\n".join(updated_sr_no)
            item.qty = len(updated_sr_no)
            item.selected_ipuids = "\n".join(updated_ipuids)
            item.selected_puids = "\n".join(updated_puids)
            break
    doc.save()
    frappe.db.commit()

@frappe.whitelist()
def attach_xlsx(name, doctype):
    doc = frappe.get_doc(doctype, name)
    all_data = []
    for item in doc.items:
        if not frappe.get_value("Item",item.item_code,"has_serial_no"):
            continue
        if doc.doctype == "Purchase Receipt":
            ipuids = item.ipuid.split("\n") if item.ipuid else []
            puids = item.puid.split("\n") if item.ipuid else []
        elif doc.doctype == "Stock Entry":
            ipuids = item.selected_ipuids.split("\n") if item.selected_ipuids else item.ipuid.split("\n")
            puids = item.selected_puids.split("\n") if item.selected_puids else item.puid.split("\n")
        else:
            ipuids = item.selected_ipuids.split("\n") if item.selected_ipuids else []
            puids = item.selected_puids.split("\n") if item.selected_puids else []
        for sr in item.serial_no.split("\n"):
            if not sr:
                continue
            all_data.append([item.item_code, doc.company,"SERIAL NO", sr, doc.posting_date.strftime("%B %d, %Y")])
        for ipuid in ipuids:
            if not ipuid:
                continue
            all_data.append([item.item_code, doc.company,"IPUID", ipuid, doc.posting_date.strftime("%B %d, %Y")])
        for puid in puids:
            if not puid:
                continue
            all_data.append([item.item_code, doc.company,"PUID", puid, doc.posting_date.strftime("%B %d, %Y")])
    df = pd.DataFrame(all_data, columns=['ITEM CODE','COMPANY','ID TYPE','SN/ID','DATE'])
    df.to_excel(f"/home/frappe/frappe-bench/sites/staging/public/files/{doc.name}.xlsx", index=False)
    doc.barcode_pdf = f"/files/{doc.name}.xlsx"
    doc.save()
    frappe.db.commit()
