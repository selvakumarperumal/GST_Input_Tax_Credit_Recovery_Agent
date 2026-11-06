from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from gst_input_tax_credit_recovery_agent.database import engine, get_session, init_db
from gst_input_tax_credit_recovery_agent.matching import reconcile
from gst_input_tax_credit_recovery_agent.models import (
    Gstr2bRecord,
    PurchaseInvoice,
    Vendor,
)
from gst_input_tax_credit_recovery_agent.parsers import (
    BadFile,
    parse_gstr2b,
    parse_purchase_register,
    parse_vendors,
)

PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"
Session = Annotated[AsyncSession, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(title="GST ITC Recovery Agent", lifespan=lifespan)


@app.exception_handler(BadFile)
async def bad_file(request: Request, error: BadFile):
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.get("/")
def hello():
    return {"message": "Hello, World!"}


@app.post("/uploads/purchase-register")
async def upload_purchase_register(
    file: UploadFile,
    period: Annotated[str, Query(pattern=PERIOD, examples=["2026-10"])],
    session: Session,
):
    """Upload the month's purchase register (.xlsx or .csv). Replaces any earlier upload for that month."""
    invoices = parse_purchase_register(file.filename, await file.read())
    await session.exec(delete(PurchaseInvoice).where(PurchaseInvoice.period == period))
    session.add_all(PurchaseInvoice(period=period, **invoice) for invoice in invoices)
    await session.commit()
    return {"period": period, "invoices": len(invoices)}


@app.post("/uploads/gstr2b")
async def upload_gstr2b(file: UploadFile, session: Session):
    """Upload a GSTR-2B JSON file from the GST portal. Replaces any earlier upload for that month."""
    period, records = parse_gstr2b(await file.read())
    await session.exec(delete(Gstr2bRecord).where(Gstr2bRecord.period == period))
    session.add_all(Gstr2bRecord(**record) for record in records)
    await session.commit()
    return {"period": period, "records": len(records)}


@app.post("/uploads/vendors")
async def upload_vendors(file: UploadFile, session: Session):
    """Upload the vendor master (.xlsx or .csv). Replaces the whole vendor list."""
    vendors = parse_vendors(file.filename, await file.read())
    await session.exec(delete(Vendor))
    session.add_all(Vendor(**vendor) for vendor in vendors)
    await session.commit()
    return {"vendors": len(vendors)}


@app.get("/reconciliation/{period}")
async def get_reconciliation(
    period: Annotated[str, Path(pattern=PERIOD, examples=["2026-10"])],
    session: Session,
):
    """Match the month's books with its GSTR-2B, and check later GSTR-2Bs for recovered credit."""
    books = (await session.exec(select(PurchaseInvoice).where(PurchaseInvoice.period == period))).all()
    if not books:
        raise HTTPException(404, f"No purchase register uploaded for {period}")
    records = (await session.exec(select(Gstr2bRecord).where(Gstr2bRecord.period == period))).all()
    later = (await session.exec(select(Gstr2bRecord).where(Gstr2bRecord.period > period).order_by(Gstr2bRecord.period))).all()
    vendors = {v.gstin: v.name for v in (await session.exec(select(Vendor))).all()}

    result = reconcile(list(books), list(records), list(later), vendors)
    result["period"] = period
    result["gstr2b_uploaded"] = bool(records)
    return _money_as_text(result)


def _money_as_text(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return {k: _money_as_text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_money_as_text(v) for v in value]
    return value
