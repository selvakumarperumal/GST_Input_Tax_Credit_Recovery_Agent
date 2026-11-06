# Example inputs

Sample data for one company and one month (**October 2026**), plus the **November 2026** GSTR-2B that shows which credit got recovered. Each mismatch type the app handles appears at least once, so you can use these files to build and test each step.

All data is made up: companies, GSTINs, emails and phone numbers. The GSTINs have valid check digits, so GSTIN validation accepts them. Emails use `example.com`.

## Files

| File | What it is | Input for |
|---|---|---|
| `purchase_register_2026-10.xlsx` / `.csv` | 11 purchase invoices booked in October, as exported from the accounts system | Purchase register upload |
| `gstr2b_2026-10.json` | October GSTR-2B: what suppliers reported | GSTR-2B upload |
| `gstr2b_2026-11.json` | November GSTR-2B: late filings and one amendment (`b2ba`) | Recovery check |
| `vendor_master.xlsx` / `.csv` | 7 vendors with contacts and preferred language | Vendor master upload |

The `.xlsx` and `.csv` versions hold the same data.

**Column names are not the app's field names.** The purchase register uses headers like an accounting export (`Party GSTIN`, `Supplier Invoice No`, …), so the column-mapping step has something to do: `Party GSTIN` → supplier GSTIN, `Supplier Invoice No` → invoice number, and so on. `Voucher No` is the company's own internal number and is not used for matching.

**GSTR-2B format:** the JSON follows the structure of the portal download (`data.docdata.b2b[].inv[].items[]`, dates as `dd-mm-yyyy`, period as `mmyyyy`) but is cut down to the fields the app needs. `chksum` is a placeholder. Check your parser against a real download before relying on it.

## The company

**Thendral Foods Private Limited**, GSTIN `33AABCT4821K1ZF` (Tamil Nadu, state code 33). Suppliers outside Tamil Nadu charge IGST; suppliers inside charge CGST + SGST.

## Expected results: October reconciliation

| # | Vendor | Invoice (books) | In October 2B | Expected result | Matched by | Tax in books | ₹ at risk |
|---|---|---|---|---|---|---|---|
| 1 | Sri Balaji Traders | `INV/2026-27/0042` | Same | ✅ Matched | Pass 1: exact | 9,000 | 0 |
| 2 | Sri Balaji Traders | `INV/2026-27/0043` | `INV-2026-27-43` | ✅ Matched | Pass 1, after normalising `/`→`-` and leading zeros | 5,760 | 0 |
| 3 | Sri Balaji Traders | `INV/2026-27/0044` | Not there | ❌ Missing in 2B | | 13,500 | 13,500 |
| 4 | Kaveri Steels | `KS-1187` | Taxable 10,000 instead of 1,00,000 | ❌ Value mismatch | | 18,000 | 16,200 (2B supports only 1,800) |
| 5 | Kaveri Steels | `KS-1190` | CGST + SGST instead of IGST | ❌ Tax head mismatch | | 9,000 | 9,000 |
| 6 | Deccan Packaging | `DP/889` (GSTIN `27AAKFD5512Q1ZZ`) | Under GSTIN `29AAKFD5512Q1ZV` | ❌ Wrong GSTIN | | 4,800 | 4,800 |
| 7 | Lotus Office Supplies | `LOS-5521` | Not there | ❌ Missing in 2B (the vendor reported it a month late, see below) | | 2,160 | 2,160 |
| 8 | Lotus Office Supplies | `LOS-5530` (02-10) | `5530` (05-10) | ✅ Matched | Pass 2: same GSTIN, same amount, date within ±7 days | 1,530 | 0 |
| 9 | Arun Electricals | `AE-3305` (17-10) | `AE-3350` (29-10) | ✅ Matched | Pass 3: same GSTIN and amount, number differs by 2 characters (date is too far off for pass 2) | 11,520 | 0 |
| 10 | Vetri Hardware | `VH-101` | Not there (vendor didn't file) | ❌ Missing in 2B | | 3,960 | 3,960 |
| 11 | Vetri Hardware | `VH-102` | Not there | ❌ Missing in 2B | | 3,240 | 3,240 |
| | | | | | **Total** | **82,470** | **52,860** |

And one record only in 2B:

| Vendor | Invoice | Expected result | Tax |
|---|---|---|---|
| Nila Logistics | `NL-778` | ⚠️ Extra in 2B: not in the books. Flag to accounts (unbooked purchase, or misuse of the GSTIN) | 2,700 |

**Check:** 27,810 matched + 1,800 supported part of `KS-1187` + 52,860 at risk = 82,470, the tax in the books.

**Vendor cases opened for October:** 5 (Sri Balaji, Kaveri, Deccan, Lotus, Vetri). Arun Electricals matched, so no case.

## Expected results: after November GSTR-2B

| Invoice | Found in November 2B? | Result | ₹ |
|---|---|---|---|
| `INV/2026-27/0044` | Yes, filed late | ✅ Recovered | 13,500 |
| `LOS-5521` | Yes, reported for November (`supprd` = `112026`) | ✅ Recovered | 2,160 |
| `KS-1187` | Yes, as an amendment in `b2ba` (original `KS-1187`, taxable now 1,00,000) | ✅ Recovered | 16,200 |
| `KS-1190` | No | Still open | 9,000 |
| `DP/889` | No | Still open (check which GSTIN is right: the books or the vendor's filing) | 4,800 |
| `VH-101`, `VH-102` | No | Still open → reminders, then escalate | 7,200 |
| | | **Recovered** | **31,860** |
| | | **Still at risk** | **21,000** |

Dashboard after November: **₹52,860 at risk → ₹31,860 recovered, ₹21,000 open.**

`INV/2026-27/0044` (forgotten, filed late) and `LOS-5521` (reported in the wrong month) look the same in the data: both simply appear in a later GSTR-2B. So both show as recovered, with `recovered_in: "2026-11"`.

## Try it with the API

Start the stack (`docker compose up --build`), then from the repo root:

```bash
curl -F file=@examples/vendor_master.xlsx localhost:8000/uploads/vendors
curl -F file=@examples/purchase_register_2026-10.xlsx "localhost:8000/uploads/purchase-register?period=2026-10"
curl -F file=@examples/gstr2b_2026-10.json localhost:8000/uploads/gstr2b
curl localhost:8000/reconciliation/2026-10        # October: ₹52,860 at risk

curl -F file=@examples/gstr2b_2026-11.json localhost:8000/uploads/gstr2b
curl localhost:8000/reconciliation/2026-10        # now: ₹31,860 recovered, ₹21,000 still at risk
```

Or use the interactive page at http://localhost:8000/docs.
