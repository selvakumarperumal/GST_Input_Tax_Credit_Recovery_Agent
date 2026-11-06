"""Reconcile the purchase register with GSTR-2B using plain matching rules."""

import re
from decimal import Decimal

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
AMOUNT_TOLERANCE = Decimal("1.00")
DATE_WINDOW_DAYS = 7
MAX_TYPO_DISTANCE = 2


def normalize_gstin(value) -> str:
    return str(value).strip().upper()


def is_valid_gstin(gstin: str) -> bool:
    if not GSTIN_PATTERN.match(gstin):
        return False
    total = 0
    for position, char in enumerate(gstin[:14]):
        product = GSTIN_CHARS.index(char) * (2 if position % 2 else 1)
        total += product // 36 + product % 36
    return gstin[14] == GSTIN_CHARS[(36 - total % 36) % 36]


def normalize_invoice_number(value) -> str:
    parts = re.split(r"[\s/\-_]+", str(value).strip().upper())
    return "-".join(part.lstrip("0") or "0" for part in parts if part)


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def total_tax(invoice) -> Decimal:
    return invoice.igst + invoice.cgst + invoice.sgst


def _same_number(book, record) -> bool:
    numbers = {normalize_invoice_number(record.invoice_number)}
    if record.original_invoice_number:
        numbers.add(normalize_invoice_number(record.original_invoice_number))
    return normalize_invoice_number(book.invoice_number) in numbers


def _close_amount(book, record) -> bool:
    return abs(book.taxable_value - record.taxable_value) <= AMOUNT_TOLERANCE


MATCHING_PASSES = [
    ("exact", lambda book, record: _same_number(book, record)),
    ("amount_and_date", lambda book, record: _close_amount(book, record)
        and abs((book.invoice_date - record.invoice_date).days) <= DATE_WINDOW_DAYS),
    ("similar_number", lambda book, record: _close_amount(book, record)
        and edit_distance(normalize_invoice_number(book.invoice_number), normalize_invoice_number(record.invoice_number)) <= MAX_TYPO_DISTANCE),
]


def find_problem(book, record) -> tuple[str | None, Decimal]:
    """Compare a book invoice with its 2B record. Returns (mismatch type or None, ₹ at risk)."""
    if record is None:
        return "missing_in_2b", total_tax(book)
    if not _close_amount(book, record) or abs(total_tax(book) - total_tax(record)) > AMOUNT_TOLERANCE:
        return "value_mismatch", max(total_tax(book) - total_tax(record), Decimal("0.00"))
    if (book.igst > 0) != (record.igst > 0):
        return "tax_head_mismatch", total_tax(book)
    return None, Decimal("0.00")


def reconcile(books: list, records: list, later_records: list, vendor_names: dict[str, str]) -> dict:
    available = list(records)
    matched = {}
    for method, rule in MATCHING_PASSES:
        for book in books:
            if book.id in matched:
                continue
            record = next((r for r in available if r.supplier_gstin == book.supplier_gstin and rule(book, r)), None)
            if record:
                matched[book.id] = (record, method)
                available.remove(record)

    lines = []
    for book in books:
        record, method = matched.get(book.id, (None, None))
        problem, at_risk = find_problem(book, record)

        if problem == "missing_in_2b":
            other = next((r for r in available if r.supplier_gstin[2:12] == book.supplier_gstin[2:12] and _same_number(book, r)), None)
            if other:
                available.remove(other)
                record, problem = other, "wrong_gstin"

        recovered_in = None
        if problem:
            fixed = next((r for r in later_records if r.supplier_gstin == book.supplier_gstin and _same_number(book, r) and find_problem(book, r)[0] is None), None)
            recovered_in = fixed.period if fixed else None

        lines.append({
            "supplier_gstin": book.supplier_gstin,
            "vendor": vendor_names.get(book.supplier_gstin, record.supplier_name if record else None),
            "invoice_number": book.invoice_number,
            "status": "matched" if not problem else "recovered" if recovered_in else "at_risk",
            "matched_by": method if not problem else None,
            "mismatch_type": problem,
            "gstr2b_invoice_number": record.invoice_number if record else None,
            "gstr2b_gstin": record.supplier_gstin if record else None,
            "tax_in_books": total_tax(book),
            "tax_in_2b": total_tax(record) if record else Decimal("0.00"),
            "itc_at_risk": at_risk,
            "recovered_in": recovered_in,
        })

    by_vendor = {}
    for line in lines:
        if line["status"] == "at_risk":
            vendor = by_vendor.setdefault(line["supplier_gstin"], {"supplier_gstin": line["supplier_gstin"], "vendor": line["vendor"], "open_invoices": 0, "itc_at_risk": Decimal("0.00")})
            vendor["open_invoices"] += 1
            vendor["itc_at_risk"] += line["itc_at_risk"]

    tax_in_books = sum((line["tax_in_books"] for line in lines), Decimal("0.00"))
    total_at_risk = sum((line["itc_at_risk"] for line in lines), Decimal("0.00"))
    recovered = sum((line["itc_at_risk"] for line in lines if line["status"] == "recovered"), Decimal("0.00"))
    return {
        "summary": {
            "invoices": len(lines),
            "matched": sum(line["status"] == "matched" for line in lines),
            "tax_in_books": tax_in_books,
            "itc_at_risk": total_at_risk,
            "recovered": recovered,
            "still_at_risk": total_at_risk - recovered,
        },
        "vendors_to_chase": sorted(by_vendor.values(), key=lambda v: v["itc_at_risk"], reverse=True),
        "invoices": lines,
        "extra_in_2b": [
            {"supplier_gstin": r.supplier_gstin, "vendor": vendor_names.get(r.supplier_gstin, r.supplier_name),
             "invoice_number": r.invoice_number, "tax": total_tax(r)}
            for r in available
        ],
    }
