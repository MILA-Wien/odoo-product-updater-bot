import base64
import csv
import logging
import os
import sys
import argparse
import functools
from decimal import Decimal

import requests as requests

from odoo import OdooAPI
import odoo_utils
import io
from ftplib import FTP

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

parser = argparse.ArgumentParser()
parser.add_argument("--all", action="store_true")
parser.add_argument("--product_id")
parser.add_argument(
    "-v",
    "--loglevel",
    default="INFO",
    help="Provide logging level. Example --loglevel debug, default=warning",
)
args = parser.parse_args()

logging.basicConfig(stream=sys.stderr, level=args.loglevel)
logger = logging.getLogger(__name__)

c = OdooAPI.get_connection()


@functools.lru_cache()
def get_uom_by_id(uom_id):
    search_result = c.search_read("uom.uom", cond=[["id", "=", uom_id]])
    return next(iter(search_result), None)


# TODO(Leon Handreke): Have a FULL/REDUCED enum here
TAXES_UST_IDS = {7: 109, 19: 108}
TAXES_VST_IDS = {7: 118, 19: 117}

INCOME_ACCOUNT_BY_TAX = {7: 1864, 19: 1874}  # 4300  # 4400
EXPENSE_ACCOUNT_BY_TAX = {7: 2025, 19: 2027}  # 5300  # 5400

TERRA_PFAND_8_CT = {"998810", "998790", "998730", "998840"}
TERRA_PFAND_15_CT = {
    "998405",
    "998040",
    "998310",
    "998320",
    "998402",
    "998340",
    "998393",
    "998060",
    "998450",
    "998352",
    "998417",
    "998352",
    "998427",
    "998366",
    "998393",
    "998370",
    "998360",
    "998420",
    "998790",
    "998405",
    "999020",
    "998398",
    "999010",
    "999020",
    "900067",
    "998408",
}

TAX_PFAND_8_CT = 176
TAX_PFAND_15_CT = 175

glutenfrei_category_id = c.get(
    "product.public.category", [("name", "=", "Glutenfrei")]
)["id"]


def read_from_terra_bnn(infile, source_name):
    products_by_ean = dict()

    reader = csv.reader(infile, delimiter=";")
    # Skip the header line with version info
    next(reader)
    for row in reader:
        # Skip last row
        if len(row) == 3:
            break

        # Add an element in the row so that the indexes given in he spec PDF (that start at 1)
        # match up with the one in the code here
        row = [None] + row
        if row[2] in [
            "X",  # ausgelistet
        ]:
            continue

        # Index by EANladen
        products_by_ean[row[5]] = {
            "artikel_nr": row[1],
            "ean_laden": row[5],
            "bezeichnung": row[7] + row[8] + row[9],
            "hersteller": row[11],
            "bestelleinheit": row[22],
            # Anzahl Ladeneinheit pro Bestelleinheit
            "bestelleinheit_menge": int(Decimal(row[23].replace(",", "."))),
            # Der Mengenfaktor ist üblicherweise 1, was bedeutet, dass sich die Preise genau auf die Ladeneinheit
            # z.B. bei Gewichtsartikeln statt kg-Preisen 100g-Preise angegeben, obwohl die Ladeneinheit kg ist, ist der
            # Mengenfaktor 0,1: alle Preise beziehen sich also auf ein Zehntel der Ladeneinheit.
            "mengenfaktor": Decimal(row[25].replace(",", ".")),
            "mwst": 7 if (row[34]) == "1" else 19,
            # Preis pro Ladeneinheit
            "preis": Decimal(row[38].replace(",", ".")),
            "pfand_nr_ladeneinheit": row[27],
            "pfand_nr_bestelleinheit": row[28],
            "grundpreis_einheit": row[66],
            "grundpreis_faktor": Decimal(row[67].replace(",", ".")),
            "source_name": source_name,
        }
    return products_by_ean


terra_ftp = FTP("order.terra-natur.com")
terra_ftp.login("", "")

terra_pl_food_file = io.BytesIO()
terra_ftp.retrbinary("RETR PL_FOOD.bnn", terra_pl_food_file.write)
terra_pl_food_file.seek(0)

terra_pl_drog_file = io.BytesIO()
terra_ftp.retrbinary("RETR PL_DROG.bnn", terra_pl_drog_file.write)
terra_pl_drog_file.seek(0)

terra_pl_frisch_file = io.BytesIO()
terra_ftp.retrbinary("RETR PL_FRISCH.bnn", terra_pl_frisch_file.write)
terra_pl_frisch_file.seek(0)

terra = {
    **read_from_terra_bnn(
        io.TextIOWrapper(terra_pl_food_file, encoding="cp850"),
        source_name="food",
    ),
    **read_from_terra_bnn(
        io.TextIOWrapper(terra_pl_drog_file, encoding="cp850"),
        source_name="drog",
    ),
    **read_from_terra_bnn(
        io.TextIOWrapper(terra_pl_frisch_file, encoding="cp850"),
        source_name="frisch",
    ),
}

agidra = dict()

def read_from_agidra_csv(infile):
    products_by_ean = dict()
    reader = csv.DictReader(infile)
    for row in reader:
        products_by_ean[row["Code EAN"]] = {
            "name": row["Désignation produit"],
            "price_sale_unit": Decimal(row["Prix/U."]),
            "vpe": int(Decimal(row["Colisage"])),
            "price_vpe": Decimal(row["P. Conditionement"]),
            "weight_sale_unit": Decimal(row["Poids brut"]),
            # Sometimes the OUM colum is empty
            "uom": row["Unité de poids"] or "KG",
            "tva": Decimal(row["TVA"]),
            "supplier_code": row["REF"],
        }
    return products_by_ean

agidra = {
    **read_from_agidra_csv(open(os.path.join(__location__, "data/agidra.csv"), mode="r")),
    **read_from_agidra_csv(open(os.path.join(__location__, "data/agidra-2021-10-27.csv"), mode="r"))
}


with open(os.path.join(__location__, "producers.csv"), mode="r") as infile:
    reader = csv.reader(infile)
    producers = {l[0]: l[1] for l in reader}

if args.all:
    search_cond = [["product_importer_script_behavior", "=", "enabled"]]
elif args.product_id:
    search_cond = [["id", "=", args.product_id]]
else:
    search_cond = [["name", "=", "NEW"], ["product_importer_script_behavior", "=", "enabled"]]

products = OdooAPI.get_connection().search_read(
    "product.template",
    search_cond,
    fields=[
        "id",
        "name",
        "barcode",
        "qty_available",
        "image",
        "product_variant_id",
        "taxes_id",
        "uom_id",
        "supplier_taxes_id",
        "standard_price",
        "property_account_income_id",
        "property_account_expense_id",
        "margin_classification_id",
        "print_category_id",
        "base_price_unit",
        "base_price_factor",
        "available_in_pos",
        "type",
        "uom_po_id",
    ],
)
supplier_infos = c.search_read(
    "product.supplierinfo",
    [],
    fields=["name", "product_name", "product_code", "product_tmpl_id", "price"],
)


def get_supplier_info_for_product(product_id):
    matching = filter(lambda si: si["product_tmpl_id"][0] == product_id, supplier_infos)
    return next(matching, None)


orderpoints = c.search_read(
    "stock.warehouse.orderpoint",
    [],
    fields=["product_min_qty", "product_max_qty", "product_id"],
)


def get_orderpoint_for_product(product_id):
    matching = filter(lambda x: x["product_id"][0] == product_id, orderpoints)
    return next(matching, None)


def compute_product_field_updates(old, updated):
    # Special handling to deal with the broken fact that odoo saves prices as floats
    if "standard_price" in old:
        old["standard_price"] = round(Decimal(str(old["standard_price"])), 2)
    if "base_price_factor" in old:
        old["base_price_factor"] = round(Decimal(str(old["base_price_factor"])), 3)

    field_updates = dict()
    for field_name in [
        "name",
        "available_in_pos",
        "standard_price",
        "type",
        "image",
        "base_price_unit",
        "base_price_factor",
    ]:
        if (field_name not in old) or (
            field_name in updated and old[field_name] != updated[field_name]
        ):
            field_updates[field_name] = updated[field_name]

    # References, they are in the format [id, name] from odoo but only id in updated
    for field_name in [
        "print_category_id",
        "margin_classification_id",
        "uom_po_id",
        "property_account_income_id",
        "property_account_expense_id",
    ]:
        if (field_name not in old) or (
            field_name in updated and (old[field_name] == False or old[field_name][0] != updated[field_name])
        ):
            field_updates[field_name] = updated[field_name]

    # Many fields, use ORM update syntax
    for field_name in ["taxes_id", "supplier_taxes_id"]:
        if (field_name not in old) or (
            field_name in updated and set(old[field_name]) != set(updated[field_name])
        ):
            field_updates[field_name] = [(6, 0, updated[field_name])]

    if "standard_price" in field_updates:
        field_updates["standard_price"] = str(field_updates["standard_price"])
    if "base_price_factor" in field_updates:
        field_updates["base_price_factor"] = str(field_updates["base_price_factor"])

    return field_updates


def compute_supplier_info_field_updates(old, updated):
    # Special handling to deal with the broken fact that odoo saves prices as floats
    if "price" in old:
        old["price"] = round(Decimal(str(old["price"])), 2)

    field_updates = dict()
    for field_name in ["product_code", "product_name", "price"]:
        if (field_name not in old) or (
            field_name in updated and old[field_name] != updated[field_name]
        ):
            field_updates[field_name] = updated[field_name]

    # References, they are in the format [id, name] from odoo but only id in updated
    for field_name in ["name", "product_tmpl_id"]:
        if (field_name not in old) or (
            field_name in updated and old[field_name][0] != updated[field_name]
        ):
            field_updates[field_name] = updated[field_name]

    if "price" in field_updates:
        field_updates["price"] = str(field_updates["price"])

    return field_updates


def update_from_terra(p):
    new_product = p["name"] == "NEW"

    barcode = p["barcode"]
    t = terra[barcode]
    vpe = t["bestelleinheit_menge"]

    # Match category of sale unit in Purchase OUM. This is to allow to switch to kg
    uom = get_uom_by_id(p["uom_id"][0])
    uom_po_id = odoo_utils.get_or_create_uom(c, vpe, uom["category_id"][0])

    ek = t["preis"] / t["mengenfaktor"]
    pfand = t["pfand_nr_ladeneinheit"] or t["pfand_nr_bestelleinheit"]

    product_name = t["bezeichnung"]
    # Some products in Terra have a weird "> " prefix
    product_name = product_name.removeprefix("> ")

    producer = (
        producers[t["hersteller"]] if t["hersteller"] in producers else t["hersteller"]
    )
    product_name += " (%s)" % producer

    mwst = t["mwst"]

    tax_ids = [TAXES_UST_IDS[mwst]]
    supplier_tax_ids = [TAXES_VST_IDS[mwst]]

    if pfand:
        product_name += " (inkl. Pfand)"
        if pfand in TERRA_PFAND_8_CT:
            tax_ids.append(TAX_PFAND_8_CT)
        elif pfand in TERRA_PFAND_15_CT:
            tax_ids.append(TAX_PFAND_15_CT)
        else:
            tax_ids.append(TAX_PFAND_15_CT)
            # Make it debug for now so that I don't get too many emails
            logger.debug(
                "Cost for Pfandeinheit %s for product %s not found.", pfand, barcode
            )

    product_fields = {
        "property_account_income_id": INCOME_ACCOUNT_BY_TAX[mwst],
        "property_account_expense_id": EXPENSE_ACCOUNT_BY_TAX[mwst],
        "taxes_id": tax_ids,
        "supplier_taxes_id": supplier_tax_ids,
        "uom_po_id": uom_po_id,
        # Pfand to Cost (to calc sales price) but not to supplier price
        "standard_price": round(ek, 2),
        "type": "product",
    }

    if new_product:
        product_fields.update(
            {
                "name": product_name,
                "available_in_pos": True,
                "print_category_id": 1,  # Print Supermarket Pricetags
                "margin_classification_id": 2
                if t["source_name"] == "frisch"
                else 1,  # 26% or General (23% Handelsspanne)
            }
        )

    if not p["image"]:
        img = requests.get(
            "https://www.terra-natur.com/_artikelbilder_/{}/{}_medium.jpg".format(
                p["barcode"], p["barcode"]
            )
        )
        img64 = base64.b64encode(img.content).decode("ascii")
        product_fields["image"] = img64

    if t["grundpreis_einheit"]:
        unit = t["grundpreis_einheit"].lower()
        if unit == "lt":
            unit = "l"
        product_fields["base_price_unit"] = unit
        product_fields["base_price_factor"] = round(t["grundpreis_faktor"], 3)

    product_fields["public_categ_ids"] = []
    # if t["e-Product Category "]:
    #     public_category = c.get('product.public.category', [('name', '=', t["e-Product Category "])])
    #     if public_category:
    #         # (4, id, ) ADD
    #         product_fields["public_categ_ids"].append((4, public_category["id"], 0))
    #     else:
    #         logger.warning("Category \"%s\" not found", t["e-Product Category "])

    # if t["Gluten"] in ["N", "S"]:
    #     product_fields["public_categ_ids"].append((4, glutenfrei_category_id, 0))

    field_updates = compute_product_field_updates(p, product_fields)
    if field_updates:
        logger.info('Updating product %d "%s": %s', p["id"], p["name"], field_updates)
        c.write("product.template", [p["id"]], field_updates)
    else:
        logger.debug('No update required for product "%s"', p["name"])

    supplier_info_fields = {
        "name": 11,  # 'Terra Naturkost Handels KG',
        "product_code": t["artikel_nr"],
        "product_name": t["bezeichnung"],
        "product_tmpl_id": p["id"],
        "price": ek * vpe,
    }
    supplier_info = get_supplier_info_for_product(p["id"])
    field_updates = compute_supplier_info_field_updates(
        supplier_info or {}, supplier_info_fields
    )
    if supplier_info:
        if field_updates:
            logger.info(
                'Updating supplierinfo %d for product "%s" %s',
                supplier_info["id"],
                p["name"],
                field_updates,
            )
            c.write("product.supplierinfo", [supplier_info["id"]], field_updates)
        else:
            logger.debug('No supplierinfo update required for product "%s"', p["name"])
    else:
        logger.info('Creating supplierinfo for product "%s"', p["name"])
        c.create("product.supplierinfo", field_updates)

    product_variant_id = p["product_variant_id"][0]
    reordering_rule = get_orderpoint_for_product(product_variant_id)
    if p["qty_available"] > 0 and not reordering_rule:
        logger.info('Creating orderpoint for product %d "%s"', p["id"], p["name"])
        c.create(
            "stock.warehouse.orderpoint",
            {
                "product_min_qty": 2.0,
                "product_max_qty": vpe,
                "product_id": p["product_variant_id"][0],
            },
        )


def update_from_agidra(p):
    new_product = p["name"] == "NEW"

    barcode = p["barcode"]
    agidra_product = agidra[barcode]
    vpe = agidra_product["vpe"]

    # Match category of sale unit in Purchase OUM. This is to allow to switch to kg
    uom = get_uom_by_id(p["uom_id"][0])
    uom_po_id = odoo_utils.get_or_create_uom(c, vpe, uom["category_id"][0])

    ek = agidra_product["price_vpe"] / vpe

    delivery_cost = Decimal("0")
    if agidra_product["uom"] in ["LIT", "KG"]:
        delivery_cost = Decimal("0.25") * agidra_product["weight_sale_unit"]
    else:
        logger.warning("Unknown uom for Agdira product: %s", agidra_product["uom"])

    mwst = 7 if agidra_product["tva"] == Decimal("5.5") else 19
    # TODO(Leon Handreke): Pull out into a function, it's the same in terra
    tax_ids = [TAXES_UST_IDS[mwst]]
    supplier_tax_ids = [TAXES_VST_IDS[mwst]]

    product_fields = {
        "property_account_income_id": INCOME_ACCOUNT_BY_TAX[mwst],
        "property_account_expense_id": EXPENSE_ACCOUNT_BY_TAX[mwst],
        "taxes_id": tax_ids,
        "supplier_taxes_id": supplier_tax_ids,
        "uom_po_id": uom_po_id,
        # Pfand to Cost (to calc sales price) but not to supplier price
        "standard_price": round(ek + delivery_cost, 2),
        "type": "product",
    }

    if new_product:
        product_fields.update(
            {
                "name": agidra_product["name"],
                "available_in_pos": True,
                "print_category_id": 1,  # Print Supermarket Pricetags
                "margin_classification_id": 1  # General (23% Handelsspanne)
            }
        )


    if not p["image"]:
        img = requests.get(
            "https://www.agidra.com/images/vignettes/{}_Z1.jpg".format(
                agidra_product["supplier_code"]
            )
        )
        img64 = base64.b64encode(img.content).decode("ascii")
        product_fields["image"] = img64

    if agidra_product["uom"]:
        unit = agidra_product["uom"].lower()
        if unit == "lit":
            unit = "l"
        product_fields["base_price_unit"] = unit
        product_fields["base_price_factor"] = round(
            Decimal("1.0") / agidra_product["weight_sale_unit"], 3
        )

    field_updates = compute_product_field_updates(p, product_fields)
    if field_updates:
        logger.info('Updating product %d "%s": %s', p["id"], p["name"], field_updates)
        c.write("product.template", [p["id"]], field_updates)
    else:
        logger.debug('No update required for product "%s"', p["name"])

    supplier_info_fields = {
        "name": 362,  # AGIDRA
        "product_code": agidra_product["supplier_code"],
        "product_name": agidra_product["name"],
        "product_tmpl_id": p["id"],
        "price": agidra_product["price_vpe"],
    }
    supplier_info = get_supplier_info_for_product(p["id"])
    field_updates = compute_supplier_info_field_updates(
        supplier_info or {}, supplier_info_fields
    )
    if supplier_info:
        if field_updates:
            logger.info(
                'Updating supplierinfo for product "%s" %s', p["name"], field_updates
            )
            c.write("product.supplierinfo", [supplier_info["id"]], field_updates)
        else:
            logger.debug('No supplierinfo update required for product "%s"', p["name"])
    else:
        logger.info('Creating supplierinfo for product "%s"', p["name"])
        c.create("product.supplierinfo", field_updates)

    product_variant_id = p["product_variant_id"][0]
    reordering_rule = get_orderpoint_for_product(product_variant_id)
    if p["qty_available"] > 0 and not reordering_rule:
        logger.info('Creating orderpoint for product "%s"', p["name"])
        c.create(
            "stock.warehouse.orderpoint",
            {
                "product_min_qty": 8.0,
                "product_max_qty": vpe,
                "product_id": p["product_variant_id"][0],
            },
        )


def update_other_products(p):
    supplier_info = get_supplier_info_for_product(p["id"])

    # If only cost is filled and supplier_info price is 0, transfer it as a convenience
    if supplier_info and p["standard_price"] != 0 and supplier_info["price"] == 0:

        uom = c.get("uom.uom", cond=[["id", "=", p["uom_po_id"][0]]])
        supplier_info_fields = {"price": p["standard_price"] * uom["factor_inv"]}

        logger.info(
            'Updating supplierinfo %d for product "%s" %s',
            supplier_info["id"],
            p["name"],
            supplier_info_fields,
        )
        c.write("product.supplierinfo", [supplier_info["id"]], supplier_info_fields)

    # Make sure Product Category follows tax setting
    mwst = None
    if TAXES_UST_IDS[7] in p["taxes_id"]:
        mwst = 7
    elif TAXES_UST_IDS[19] in p["taxes_id"]:
        mwst = 19

    if mwst:
        income_account_correct = (
            p["property_account_income_id"]
            and p["property_account_income_id"][0] == INCOME_ACCOUNT_BY_TAX[mwst]
        )
        expense_account_correct = (
            p["property_account_expense_id"]
            and p["property_account_expense_id"][0] == EXPENSE_ACCOUNT_BY_TAX[mwst]
        )
        if not (income_account_correct and expense_account_correct):
            product_fields = {
                "property_account_income_id": INCOME_ACCOUNT_BY_TAX[mwst],
                "property_account_expense_id": EXPENSE_ACCOUNT_BY_TAX[mwst],
            }
            logger.info('Updating product "%s": %s', p["name"], product_fields)
            c.write("product.template", [p["id"]], product_fields)


if __name__ == "__main__":
    for p in products:
        if p["barcode"] in terra:
            update_from_terra(p)
        elif p["barcode"] in agidra:
            update_from_agidra(p)
        else:
            update_other_products(p)

    translations_to_delete = [
        t["id"]
        for t in c.search_read(
            "ir.translation", [["name", "=", "product.template,name"]]
        )
    ]
    c.unlink("ir.translation", translations_to_delete)
