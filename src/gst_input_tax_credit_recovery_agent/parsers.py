"""Read uploaded files (CSV, Excel, GSTR-2B JSON) into plain dicts."""

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook

from gst_input_tax_credit_recovery_agent.matching import is_valid_gstin, normalize_gstin

PURCHASE_REGISTER_COLUMNS = {
    "supplier_gstin": ["supplier gstin", "party gstin", "vendor gstin", "gstin of supplier", "gstin"],
    "invoice_number": ["supplier invoice no", "invoice number", "invoice no", "bill no", "inv no"],
    "invoice_date": ["supplier invoice date", "invoice date", "bill date", "date"],
    "taxable_value": ["taxable value", "taxable amount", "taxable"],
    "igst": ["igst", "igst amount"],
    "cgst": ["cgst", "cgst amount"],
    "sgst": ["sgst", "sgst amount"],
}

VENDOR_COLUMNS = {
    "gstin": ["gstin", "vendor gstin", "party gstin"],
    "name": ["vendor name", "party name", "name"],
    "email": ["email", "email id"],
    "phone": ["phone", "mobile", "phone number"],
    "language": ["preferred language", "language"],
}


class BadFile(Exception):
    """The uploaded file can't be used; the message says why."""


def parse_purchase_register(filename: str, content: bytes) -> list[dict]:
    rows = _map_columns(_read_table(filename, content), PURCHASE_REGISTER_COLUMNS)
    invoices = []
    for line, row in enumerate(rows, start=2):
        gstin = normalize_gstin(row["supplier_gstin"])
        if not is_valid_gstin(gstin):
            raise BadFile(f"Row {line}: invalid supplier GSTIN '{row['supplier_gstin']}'")
        invoices.append({
            "supplier_gstin": gstin,
            "invoice_number": str(row["invoice_number"]).strip(),
            "invoice_date": _to_date(row["invoice_date"], line),
            "taxable_value": _to_money(row["taxable_value"], line),
            "igst": _to_money(row.get("igst"), line),
            "cgst": _to_money(row.get("cgst"), line),
            "sgst": _to_money(row.get("sgst"), line),
        })
    return invoices


def parse_vendors(filename: str, content: bytes) -> list[dict]:
    rows = _map_columns(_read_table(filename, content), VENDOR_COLUMNS, optional={"email", "phone", "language"})
    vendors = []
    for line, row in enumerate(rows, start=2):
        gstin = normalize_gstin(row["gstin"])
        if not is_valid_gstin(gstin):
            raise BadFile(f"Row {line}: invalid GSTIN '{row['gstin']}'")
        vendors.append({
            "gstin": gstin,
            "name": str(row["name"]).strip(),
            "email": row.get("email") or None,
            "phone": str(row["phone"]) if row.get("phone") else None,
            "language": row.get("language") or "English",
        })
    return vendors


def parse_gstr2b(content: bytes) -> tuple[str, list[dict]]:
    try:
        data = json.loads(content)["data"]
        return_period = data["rtnprd"]
        period = f"{return_period[2:]}-{return_period[:2]}"
        records = []
        for section in ("b2b", "b2ba"):
            for supplier in data["docdata"].get(section, []):
                for invoice in supplier["inv"]:
                    amounts = invoice.get("items") or [invoice]
                    records.append({
                        "period": period,
                        "section": section,
                        "supplier_gstin": normalize_gstin(supplier["ctin"]),
                        "supplier_name": supplier.get("trdnm"),
                        "invoice_number": invoice["inum"],
                        "original_invoice_number": invoice.get("oinum"),
                        "invoice_date": datetime.strptime(invoice["dt"], "%d-%m-%Y").date(),
                        "taxable_value": _sum(amounts, "txval"),
                        "igst": _sum(amounts, "igst"),
                        "cgst": _sum(amounts, "cgst"),
                        "sgst": _sum(amounts, "sgst"),
                    })
    except (ValueError, KeyError, TypeError) as error:
        raise BadFile(f"Not a valid GSTR-2B JSON file ({error})") from error
    return period, records


def _read_table(filename: str, content: bytes) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    elif filename.lower().endswith(".csv"):
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    else:
        raise BadFile("Upload a .csv or .xlsx file")
    if not rows:
        raise BadFile("The file is empty")
    headers = [" ".join(str(h or "").lower().split()) for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:] if any(cell not in (None, "") for cell in row)]


def _map_columns(rows: list[dict], columns: dict[str, list[str]], optional=frozenset({"igst", "cgst", "sgst"})) -> list[dict]:
    headers = rows[0].keys() if rows else []
    mapping = {}
    for field, names in columns.items():
        found = next((name for name in names if name in headers), None)
        if found:
            mapping[field] = found
        elif field not in optional:
            raise BadFile(f"Missing a column for '{field}'. Accepted names: {names}. Found: {list(headers)}")
    return [{field: row[header] for field, header in mapping.items()} for row in rows]


def _to_date(value, line: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            pass
    raise BadFile(f"Row {line}: can't read date '{value}' (use YYYY-MM-DD or DD-MM-YYYY)")


def _to_money(value, line: int) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise BadFile(f"Row {line}: can't read amount '{value}'") from None


def _sum(items: list[dict], key: str) -> Decimal:
    return sum((Decimal(str(item.get(key) or 0)) for item in items), Decimal(0)).quantize(Decimal("0.01"))
