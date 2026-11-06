from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel


class Vendor(SQLModel, table=True):
    __tablename__ = "vendors"

    gstin: str = Field(primary_key=True, max_length=15)
    name: str
    email: str | None = None
    phone: str | None = None
    language: str = "English"


class PurchaseInvoice(SQLModel, table=True):
    __tablename__ = "purchase_invoices"

    id: int | None = Field(default=None, primary_key=True)
    period: str = Field(index=True)
    supplier_gstin: str = Field(index=True, max_length=15)
    invoice_number: str
    invoice_date: date
    taxable_value: Decimal = Field(max_digits=14, decimal_places=2)
    igst: Decimal = Field(default=0, max_digits=14, decimal_places=2)
    cgst: Decimal = Field(default=0, max_digits=14, decimal_places=2)
    sgst: Decimal = Field(default=0, max_digits=14, decimal_places=2)


class Gstr2bRecord(SQLModel, table=True):
    __tablename__ = "gstr2b_records"

    id: int | None = Field(default=None, primary_key=True)
    period: str = Field(index=True)
    section: str
    supplier_gstin: str = Field(index=True, max_length=15)
    supplier_name: str | None = None
    invoice_number: str
    original_invoice_number: str | None = None
    invoice_date: date
    taxable_value: Decimal = Field(max_digits=14, decimal_places=2)
    igst: Decimal = Field(default=0, max_digits=14, decimal_places=2)
    cgst: Decimal = Field(default=0, max_digits=14, decimal_places=2)
    sgst: Decimal = Field(default=0, max_digits=14, decimal_places=2)
