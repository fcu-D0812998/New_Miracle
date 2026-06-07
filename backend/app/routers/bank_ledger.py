"""銀行帳本與對帳 API。"""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.accounting_period import accounting_period_for_date, apply_accounting_period_filter
from app.billing import apply_invoice_tax, calculate_receivable_status, invoice_tax_amount
from app.database import get_connection, get_cursor

router = APIRouter()

RECEIVABLE_UNPAID = "未收"
RECEIVABLE_PARTIAL = "部分收款"
RECEIVABLE_PAID = "已收款"

PAYABLE_STATUS_MAP = {
    RECEIVABLE_UNPAID: "未付款",
    RECEIVABLE_PARTIAL: "部分付款",
    RECEIVABLE_PAID: "已付款",
}


class BankLedgerBase(BaseModel):
    txn_date: date
    payer: Optional[str] = None
    expense: float = 0
    income: float = 0
    note: Optional[str] = None
    is_reconciled: bool = False
    reconciled_ar_id: Optional[int] = None
    reconciled_ar_type: Optional[str] = None
    reconciled_payable_contract_code: Optional[str] = None
    reconciled_payable_type: Optional[str] = None
    reconciled_service_expense_id: Optional[int] = None
    reconciled_fee_amount: float = 0


class ReconciliationLineInput(BaseModel):
    target_id: int
    allocated_amount: float
    fee_amount: float = 0
    ar_type: Optional[str] = None


class ReconcileRequest(BaseModel):
    reconcile_type: str  # "receivable" 或 "service_expense"
    lines: List[ReconciliationLineInput] = Field(default_factory=list)
    ar_id: Optional[int] = None
    ar_type: Optional[str] = None
    service_expense_id: Optional[int] = None
    fee_amount: float = 0
    auto_update: bool = True


class OcrImageInput(BaseModel):
    filename: str
    content_base64: str
    mime_type: Optional[str] = None


class OcrPreviewRequest(BaseModel):
    images: List[OcrImageInput]


class OcrDraftRow(BaseModel):
    txn_date: date
    payer: Optional[str] = None
    expense: float = 0
    income: float = 0
    note: Optional[str] = None


class OcrImportRequest(BaseModel):
    rows: List[OcrDraftRow]


class BankLedgerCreate(BankLedgerBase):
    pass


class BankLedgerUpdate(BankLedgerBase):
    pass


class BankLedger(BankLedgerBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _to_float(value) -> float:
    return float(value) if value is not None else 0.0


def _round_money(value) -> float:
    return round(_to_float(value), 2)


def _normalize_ar_type(ar_type: Optional[str]) -> Optional[str]:
    if not ar_type:
        return None
    value = str(ar_type).strip().lower()
    if value in {"租賃", "租赁", "leasing", "lease"}:
        return "租賃"
    if value in {"買斷", "买断", "buyout"}:
        return "買斷"
    return None


def _calculate_receivable_status(amount: float, fee: float, received_amount: float,
                                 needs_invoice: bool = False) -> str:
    return calculate_receivable_status(amount, fee, received_amount, needs_invoice)


def _calculate_service_status(amount: float, paid_amount: float) -> str:
    total_due = max(_to_float(amount), 0.0)
    paid = max(_to_float(paid_amount), 0.0)
    if paid >= total_due and total_due > 0:
        return RECEIVABLE_PAID
    if paid > 0:
        return RECEIVABLE_PARTIAL
    return RECEIVABLE_UNPAID


def _service_status_to_display(status: Optional[str]) -> Optional[str]:
    return PAYABLE_STATUS_MAP.get(status, status)


def _strip_base64_prefix(value: str) -> str:
    content = (value or "").strip()
    if "," in content and content.lower().startswith("data:"):
        return content.split(",", 1)[1]
    return content


def _safe_decode_base64(value: str, filename: str) -> str:
    content = _strip_base64_prefix(value)
    try:
        base64.b64decode(content, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{filename} 圖片內容不是有效的 base64") from exc
    return content


def _call_google_vision_ocr(images: List[OcrImageInput]) -> List[dict]:
    api_key = os.getenv("GOOGLE_VISION_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="尚未設定 GOOGLE_VISION_API_KEY")
    if not images:
        raise HTTPException(status_code=400, detail="請至少上傳一張照片")
    if len(images) > 5:
        raise HTTPException(status_code=400, detail="一次最多辨識 5 張照片")

    requests = []
    for image in images:
        requests.append({
            "image": {"content": _safe_decode_base64(image.content_base64, image.filename)},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["zh-TW", "en"]},
        })

    url = "https://vision.googleapis.com/v1/images:annotate?key=" + urllib.parse.quote(api_key)
    request = urllib.request.Request(
        url,
        data=json.dumps({"requests": requests}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Google Vision OCR 失敗：{error_body}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Vision OCR 連線失敗：{exc}") from exc

    responses = payload.get("responses", [])
    for index, response_item in enumerate(responses):
        if response_item.get("error"):
            message = response_item["error"].get("message", "未知錯誤")
            filename = images[index].filename if index < len(images) else "圖片"
            raise HTTPException(status_code=502, detail=f"{filename} OCR 失敗：{message}")
    return responses


def _parse_roc_or_gregorian_date(value: str) -> Optional[date]:
    digits = re.sub(r"\D", "", value or "")
    candidates = []
    if len(digits) >= 7:
        candidates.append(digits[:7])
    if len(digits) >= 8:
        candidates.append(digits[:8])

    for candidate in candidates:
        try:
            if len(candidate) == 7:
                year = int(candidate[:3]) + 1911
                month = int(candidate[3:5])
                day = int(candidate[5:7])
            else:
                year = int(candidate[:4])
                month = int(candidate[4:6])
                day = int(candidate[6:8])
            if 2000 <= year <= 2100:
                return date(year, month, day)
        except ValueError:
            continue
    return None


def _parse_money(value: str) -> Optional[float]:
    normalized = (value or "").replace(",", "").replace("$", "").replace("＄", "")
    normalized = re.sub(r"[^\d.]", "", normalized)
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _money_candidates(text: str) -> List[float]:
    pattern = r"[$＄]?\s*\d{1,3}(?:,\d{3})+(?:\.\d+)?|[$＄]?\s*\d+(?:\.\d+)?"
    result = []
    for match in re.findall(pattern, text or ""):
        amount = _parse_money(match)
        if amount is not None and amount > 0:
            result.append(amount)
    return result


def _annotation_center(annotation: dict) -> tuple[float, float]:
    vertices = annotation.get("boundingPoly", {}).get("vertices", [])
    xs = [vertex.get("x", 0) for vertex in vertices]
    ys = [vertex.get("y", 0) for vertex in vertices]
    return (sum(xs) / len(xs) if xs else 0.0, sum(ys) / len(ys) if ys else 0.0)


def _annotation_height(annotation: dict) -> float:
    vertices = annotation.get("boundingPoly", {}).get("vertices", [])
    ys = [vertex.get("y", 0) for vertex in vertices]
    return (max(ys) - min(ys)) if ys else 20.0


def _extract_words(response_item: dict) -> List[dict]:
    annotations = response_item.get("textAnnotations", [])[1:]
    words = []
    max_x = 1.0
    for annotation in annotations:
        text = annotation.get("description", "").strip()
        if not text:
            continue
        center_x, center_y = _annotation_center(annotation)
        height = _annotation_height(annotation)
        max_x = max(max_x, center_x)
        words.append({"text": text, "x": center_x, "y": center_y, "height": height})

    if not words:
        return []

    image_width = max(word["x"] for word in words) or max_x
    for word in words:
        word["nx"] = word["x"] / image_width
    return words


def _cluster_words_by_row(words: List[dict]) -> List[List[dict]]:
    if not words:
        return []
    heights = sorted(word["height"] for word in words if word["height"] > 0)
    median_height = heights[len(heights) // 2] if heights else 20.0
    threshold = max(12.0, median_height * 0.75)
    rows: List[List[dict]] = []

    for word in sorted(words, key=lambda item: item["y"]):
        matched_row = None
        for row in rows:
            row_y = sum(item["y"] for item in row) / len(row)
            if abs(word["y"] - row_y) <= threshold:
                matched_row = row
                break
        if matched_row is None:
            rows.append([word])
        else:
            matched_row.append(word)

    for row in rows:
        row.sort(key=lambda item: item["x"])
    return rows


def _column_centers(words: List[dict]) -> dict:
    defaults = {"withdrawal": 0.58, "deposit": 0.70, "balance": 0.88}
    aliases = {
        "withdrawal": {"支出", "WITHDRAWAL", "WITHDRAW", "提款"},
        "deposit": {"存入", "DEPOSIT", "存款"},
        "balance": {"餘額", "余额", "BALANCE"},
    }
    centers = {}
    for key, keywords in aliases.items():
        matched = [
            word["nx"]
            for word in words
            if any(keyword.lower() in word["text"].lower() for keyword in keywords)
        ]
        if matched:
            centers[key] = sum(matched) / len(matched)
    return {**defaults, **centers}


def _assign_amount_column(word: dict, centers: dict) -> str:
    candidates = {
        "withdrawal": abs(word["nx"] - centers["withdrawal"]),
        "deposit": abs(word["nx"] - centers["deposit"]),
        "balance": abs(word["nx"] - centers["balance"]),
    }
    return min(candidates, key=candidates.get)


def _row_text(row: List[dict]) -> str:
    return " ".join(word["text"] for word in sorted(row, key=lambda item: item["x"])).strip()


def _draft_row(row_date: date, payer: str, expense: float, income: float,
               note: str, source_text: str, filename: str) -> dict:
    return {
        "key": f"{filename}-{row_date.isoformat()}-{abs(hash(source_text))}",
        "txn_date": row_date.isoformat(),
        "payer": payer or None,
        "expense": round(expense or 0, 2),
        "income": round(income or 0, 2),
        "note": note or None,
        "source_text": source_text,
        "source_file": filename,
    }


def _parse_rows_from_words(response_item: dict, filename: str) -> List[dict]:
    words = _extract_words(response_item)
    centers = _column_centers(words)
    rows = _cluster_words_by_row(words)
    parsed_rows: List[dict] = []
    last_row = None

    for row in rows:
        source_text = _row_text(row)
        row_date = None
        for word in row:
            candidate_date = _parse_roc_or_gregorian_date(word["text"])
            if candidate_date and word["nx"] < 0.35:
                row_date = candidate_date
                break

        if not row_date:
            if last_row and ("附言" in source_text or "備註" in source_text):
                extra_note = re.sub(r"^(附言|備註)[:：]?", "", source_text).strip()
                if extra_note:
                    last_row["note"] = " ".join(filter(None, [last_row.get("note"), extra_note]))
            continue

        withdrawal = 0.0
        deposit = 0.0
        memo_words = []
        for word in row:
            if _parse_roc_or_gregorian_date(word["text"]) and word["nx"] < 0.35:
                continue
            amount = _parse_money(word["text"])
            if amount is not None and word["nx"] >= 0.45:
                column = _assign_amount_column(word, centers)
                if column == "withdrawal":
                    withdrawal = amount
                elif column == "deposit":
                    deposit = amount
                continue
            if word["nx"] < centers["balance"] - 0.06:
                memo_words.append(word["text"])

        memo = " ".join(memo_words).strip()
        payer = memo.split()[0] if memo else ""
        draft = _draft_row(row_date, payer, withdrawal, deposit, memo, source_text, filename)
        parsed_rows.append(draft)
        last_row = draft

    return parsed_rows


def _parse_rows_from_text(raw_text: str, filename: str) -> List[dict]:
    parsed_rows = []
    last_row = None
    for line in (raw_text or "").splitlines():
        source_text = line.strip()
        if not source_text:
            continue
        date_match = re.search(r"\b\d{7,8}\b", source_text)
        row_date = _parse_roc_or_gregorian_date(date_match.group(0)) if date_match else None
        if not row_date:
            if last_row and ("附言" in source_text or "備註" in source_text):
                extra_note = re.sub(r"^(附言|備註)[:：]?", "", source_text).strip()
                if extra_note:
                    last_row["note"] = " ".join(filter(None, [last_row.get("note"), extra_note]))
            continue

        amounts = _money_candidates(source_text)
        transaction_amount = amounts[-2] if len(amounts) >= 2 else (amounts[0] if amounts else 0.0)
        expense = transaction_amount if "手續費" in source_text else 0.0
        income = 0.0 if expense else transaction_amount
        memo = re.sub(r"\b\d{7,8}\b", "", source_text)
        memo = re.sub(r"[$＄]?\s*\d{1,3}(?:,\d{3})+(?:\.\d+)?", "", memo).strip()
        payer = memo.split()[0] if memo else ""
        draft = _draft_row(row_date, payer, expense, income, memo, source_text, filename)
        parsed_rows.append(draft)
        last_row = draft
    return parsed_rows


def _parse_ocr_response(response_item: dict, filename: str) -> dict:
    raw_text = (
        response_item.get("fullTextAnnotation", {}).get("text")
        or (response_item.get("textAnnotations") or [{}])[0].get("description", "")
    )
    rows = _parse_rows_from_words(response_item, filename)
    if not rows:
        rows = _parse_rows_from_text(raw_text, filename)
    return {"filename": filename, "raw_text": raw_text, "rows": rows}


def _legacy_reconciled_amount(income: float, expense: float, is_reconciled: bool,
                              reconciled_ar_id: Optional[int],
                              reconciled_service_expense_id: Optional[int],
                              reconciled_payable_contract_code: Optional[str]) -> float:
    if not is_reconciled:
        return 0.0
    if not (reconciled_ar_id or reconciled_service_expense_id or reconciled_payable_contract_code):
        return 0.0
    return income if income > 0 else expense


def _serialize_line_row(row) -> dict:
    return {
        "id": row[0],
        "bank_ledger_id": row[1],
        "target_type": row[2],
        "target_id": row[3],
        "ar_type": row[4],
        "allocated_amount": _to_float(row[5]),
        "fee_amount": _to_float(row[6]),
        "contract_code": row[7],
        "customer_name": row[8],
        "item_type": row[9],
        "period": row[10],
        "description": row[11],
        "payee_name": row[12],
    }


def _fetch_reconciliation_lines_map(cur, ledger_ids: List[int]) -> Dict[int, List[dict]]:
    if not ledger_ids:
        return {}

    cur.execute("""
        SELECT
            line.id,
            line.bank_ledger_id,
            line.target_type,
            line.target_id,
            line.ar_type,
            line.allocated_amount,
            line.fee_amount,
            CASE
                WHEN line.target_type = 'receivable' AND line.ar_type = '租賃' THEN al.contract_code
                WHEN line.target_type = 'receivable' AND line.ar_type = '買斷' THEN ab.contract_code
                WHEN line.target_type = 'service_expense' THEN se.contract_code
            END AS contract_code,
            CASE
                WHEN line.target_type = 'receivable' AND line.ar_type = '租賃' THEN al.customer_name
                WHEN line.target_type = 'receivable' AND line.ar_type = '買斷' THEN ab.customer_name
                WHEN line.target_type = 'service_expense' THEN se.customer_name
            END AS customer_name,
            CASE
                WHEN line.target_type = 'receivable' THEN '應收帳款'
                WHEN COALESCE(se.expense_source, 'contract') = 'extra'
                    THEN COALESCE(NULLIF(se.expense_category, ''), '額外開銷')
                ELSE se.service_type
            END AS item_type,
            CASE
                WHEN line.target_type = 'receivable' AND line.ar_type = '租賃' THEN
                    CASE
                        WHEN al.end_date IS NOT NULL THEN to_char(al.start_date, 'YYYY-MM-DD') || ' ~ ' || to_char(al.end_date, 'YYYY-MM-DD')
                        ELSE to_char(al.start_date, 'YYYY-MM-DD')
                    END
                WHEN line.target_type = 'receivable' AND line.ar_type = '買斷' THEN to_char(ab.deal_date, 'YYYY-MM-DD')
                WHEN line.target_type = 'service_expense' THEN to_char(se.service_date, 'YYYY-MM-DD')
            END AS period,
            COALESCE(se.expense_description, '') AS description,
            CASE
                WHEN line.target_type = 'service_expense' THEN
                    COALESCE(
                        NULLIF(company.name, ''),
                        NULLIF(se.vendor_name, ''),
                        NULLIF(se.repair_company_code, ''),
                        '未指定付款對象'
                    )
            END AS payee_name
        FROM bank_ledger_reconciliation_lines line
        LEFT JOIN ar_leasing al
            ON line.target_type = 'receivable'
           AND line.ar_type = '租賃'
           AND line.target_id = al.id
        LEFT JOIN ar_buyout ab
            ON line.target_type = 'receivable'
           AND line.ar_type = '買斷'
           AND line.target_id = ab.id
        LEFT JOIN service_expense se
            ON line.target_type = 'service_expense'
           AND line.target_id = se.id
        LEFT JOIN companies company
            ON line.target_type = 'service_expense'
           AND company.company_code = se.repair_company_code
        WHERE line.bank_ledger_id = ANY(%s)
        ORDER BY line.bank_ledger_id, line.id
    """, (ledger_ids,))

    result: Dict[int, List[dict]] = {}
    for row in cur.fetchall():
        item = _serialize_line_row(row)
        result.setdefault(item["bank_ledger_id"], []).append(item)
    return result


def _row_to_ledger(row, line_map: Optional[Dict[int, List[dict]]] = None) -> dict:
    income = _to_float(row[4])
    expense = _to_float(row[3])
    line_count = int(row[15]) if row[15] is not None else 0
    reconciled_amount = _to_float(row[16])
    fee_total = _to_float(row[17])

    if line_count == 0:
        reconciled_amount = _legacy_reconciled_amount(
            income,
            expense,
            bool(row[6]),
            row[7],
            row[11],
            row[9],
        )
        fee_total = _to_float(row[12]) if bool(row[6]) else 0.0

    base_amount = income if income > 0 else expense
    ledger_used_amount = reconciled_amount + (fee_total if expense > 0 else 0.0)
    unallocated_amount = max(base_amount - ledger_used_amount, 0.0)

    return {
        "id": row[0],
        "txn_date": row[1].strftime("%Y-%m-%d") if row[1] else None,
        "payer": row[2],
        "expense": expense,
        "income": income,
        "note": row[5],
        "is_reconciled": bool(row[6]) if row[6] is not None else False,
        "reconciled_ar_id": row[7],
        "reconciled_ar_type": row[8],
        "reconciled_payable_contract_code": row[9],
        "reconciled_payable_type": row[10],
        "reconciled_service_expense_id": row[11],
        "reconciled_fee_amount": _to_float(row[12]),
        "created_at": row[13].strftime("%Y-%m-%d %H:%M:%S") if row[13] else None,
        "updated_at": row[14].strftime("%Y-%m-%d %H:%M:%S") if row[14] else None,
        "reconciliation_count": line_count if line_count > 0 else (1 if bool(row[6]) else 0),
        "reconciled_amount": reconciled_amount,
        "reconciled_fee_total": fee_total,
        "unallocated_amount": unallocated_amount,
        "reconciliation_lines": (line_map or {}).get(row[0], []),
        "accounting_period": row[18],
    }


def _fetch_ledger_rows(cur, from_date: Optional[str] = None,
                       to_date: Optional[str] = None,
                       search: Optional[str] = None,
                       ledger_id: Optional[int] = None,
                       accounting_period: Optional[str] = "current"):
    where_parts = []
    params = []

    if ledger_id is not None:
        where_parts.append("ledger.id = %s")
        params.append(ledger_id)
    if from_date:
        where_parts.append("ledger.txn_date >= %s")
        params.append(from_date)
    if to_date:
        where_parts.append("ledger.txn_date <= %s")
        params.append(to_date)
    if search:
        where_parts.append("(ledger.payer ILIKE %s OR ledger.note ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if ledger_id is None:
        apply_accounting_period_filter(where_parts, params, "ledger.accounting_period", accounting_period)

    where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""

    cur.execute(f"""
        SELECT
            ledger.id,
            ledger.txn_date,
            ledger.payer,
            ledger.expense,
            ledger.income,
            ledger.note,
            ledger.is_reconciled,
            ledger.reconciled_ar_id,
            ledger.reconciled_ar_type,
            ledger.reconciled_payable_contract_code,
            ledger.reconciled_payable_type,
            ledger.reconciled_service_expense_id,
            ledger.reconciled_fee_amount,
            ledger.created_at,
            ledger.updated_at,
            COALESCE(stats.line_count, 0) AS line_count,
            COALESCE(stats.allocated_amount, 0) AS reconciled_amount,
            COALESCE(stats.fee_total, 0) AS fee_total,
            COALESCE(ledger.accounting_period, 'current') AS accounting_period
        FROM bank_ledger ledger
        LEFT JOIN (
            SELECT
                bank_ledger_id,
                COUNT(*) AS line_count,
                COALESCE(SUM(allocated_amount), 0) AS allocated_amount,
                COALESCE(SUM(fee_amount), 0) AS fee_total
            FROM bank_ledger_reconciliation_lines
            GROUP BY bank_ledger_id
        ) stats ON stats.bank_ledger_id = ledger.id
        {where_clause}
        ORDER BY ledger.txn_date DESC, ledger.id DESC
    """, tuple(params))
    return cur.fetchall()


def _fetch_ledger_detail(cur, ledger_id: int) -> dict:
    rows = _fetch_ledger_rows(cur, ledger_id=ledger_id, accounting_period="all")
    if not rows:
        raise HTTPException(status_code=404, detail="銀行帳本資料不存在")
    line_map = _fetch_reconciliation_lines_map(cur, [ledger_id])
    return _row_to_ledger(rows[0], line_map)


@router.get("", response_model=List[dict])
def get_bank_ledger(
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="搜尋關鍵字"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    with get_cursor() as cur:
        rows = _fetch_ledger_rows(
            cur,
            from_date=from_date,
            to_date=to_date,
            search=search,
            accounting_period=accounting_period,
        )
        line_map = _fetch_reconciliation_lines_map(cur, [row[0] for row in rows])
        return [_row_to_ledger(row, line_map) for row in rows]


@router.get("/payers", response_model=List[str])
def get_bank_ledger_payers(
    search: Optional[str] = Query(None, description="搜尋對象/匯款人"),
):
    where_parts = ["NULLIF(TRIM(payer), '') IS NOT NULL"]
    params = []
    if search:
        where_parts.append("payer ILIKE %s")
        params.append(f"%{search}%")
    where_clause = " WHERE " + " AND ".join(where_parts)

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT TRIM(payer) AS payer_name
            FROM bank_ledger
            {where_clause}
            ORDER BY payer_name
        """, tuple(params))
        return [row[0] for row in cur.fetchall()]


@router.post("/ocr/preview", response_model=dict)
def preview_bank_ledger_ocr(payload: OcrPreviewRequest):
    responses = _call_google_vision_ocr(payload.images)
    parsed_images = []
    draft_rows = []

    for image, response_item in zip(payload.images, responses):
        parsed = _parse_ocr_response(response_item, image.filename)
        parsed_images.append({
            "filename": parsed["filename"],
            "raw_text": parsed["raw_text"],
            "row_count": len(parsed["rows"]),
        })
        draft_rows.extend(parsed["rows"])

    return {
        "images": parsed_images,
        "rows": draft_rows,
        "row_count": len(draft_rows),
        "warnings": [
            "OCR 結果可能受照片角度、陰影與手寫字影響，請逐筆確認後再匯入。"
        ],
    }


@router.post("/ocr/import", response_model=dict, status_code=201)
def import_bank_ledger_ocr_rows(payload: OcrImportRequest):
    if not payload.rows:
        raise HTTPException(status_code=400, detail="沒有可匯入的銀行帳本資料")

    conn = get_connection()
    inserted_ids = []
    try:
        with conn.cursor() as cur:
            for row in payload.rows:
                expense = max(_to_float(row.expense), 0.0)
                income = max(_to_float(row.income), 0.0)
                if expense <= 0 and income <= 0:
                    raise HTTPException(status_code=400, detail="每筆資料至少需有收入或支出金額")

                cur.execute("""
                    INSERT INTO bank_ledger
                    (txn_date, payer, expense, income, note, is_reconciled,
                     reconciled_ar_id, reconciled_ar_type,
                     reconciled_payable_contract_code, reconciled_payable_type,
                     reconciled_service_expense_id, reconciled_fee_amount, accounting_period)
                    VALUES (%s, %s, %s, %s, %s, FALSE, NULL, NULL, NULL, NULL, NULL, 0, %s)
                    RETURNING id
                """, (
                    row.txn_date,
                    (row.payer or "").strip() or None,
                    expense,
                    income,
                    (row.note or "").strip() or None,
                    accounting_period_for_date(row.txn_date),
                ))
                inserted_ids.append(cur.fetchone()[0])

            conn.commit()
            return {"inserted_count": len(inserted_ids), "ids": inserted_ids}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.post("", response_model=dict, status_code=201)
def create_bank_ledger(ledger: BankLedgerCreate):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bank_ledger
                (txn_date, payer, expense, income, note, is_reconciled,
                 reconciled_ar_id, reconciled_ar_type,
                 reconciled_payable_contract_code, reconciled_payable_type,
                 reconciled_service_expense_id, reconciled_fee_amount, accounting_period)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                ledger.txn_date,
                ledger.payer,
                ledger.expense,
                ledger.income,
                ledger.note,
                ledger.is_reconciled,
                ledger.reconciled_ar_id,
                ledger.reconciled_ar_type,
                ledger.reconciled_payable_contract_code,
                ledger.reconciled_payable_type,
                ledger.reconciled_service_expense_id,
                ledger.reconciled_fee_amount,
                accounting_period_for_date(ledger.txn_date),
            ))
            new_id = cur.fetchone()[0]
            conn.commit()
            return _fetch_ledger_detail(cur, new_id)
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.put("/{id}", response_model=dict)
def update_bank_ledger(id: int, ledger: BankLedgerUpdate):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bank_ledger
                SET txn_date = %s,
                    payer = %s,
                    expense = %s,
                    income = %s,
                    note = %s,
                    is_reconciled = %s,
                    reconciled_ar_id = %s,
                    reconciled_ar_type = %s,
                    reconciled_payable_contract_code = %s,
                    reconciled_payable_type = %s,
                    reconciled_service_expense_id = %s,
                    reconciled_fee_amount = %s,
                    accounting_period = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                ledger.txn_date,
                ledger.payer,
                ledger.expense,
                ledger.income,
                ledger.note,
                ledger.is_reconciled,
                ledger.reconciled_ar_id,
                ledger.reconciled_ar_type,
                ledger.reconciled_payable_contract_code,
                ledger.reconciled_payable_type,
                ledger.reconciled_service_expense_id,
                ledger.reconciled_fee_amount,
                accounting_period_for_date(ledger.txn_date),
                id,
            ))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="銀行帳本資料不存在")
            conn.commit()
            return _fetch_ledger_detail(cur, id)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.delete("/{id}", status_code=204)
def delete_bank_ledger(id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bank_ledger WHERE id = %s", (id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="銀行帳本資料不存在")
            conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.get("/reconcilable/receivables")
def get_reconcilable_receivables(
    search: Optional[str] = Query(None, description="搜尋關鍵字（合約編號/客戶名稱）"),
    type: Optional[str] = Query(None, description="類型（租賃/買斷）"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    result = []
    with get_cursor() as cur:
        if not type or type == "租賃":
            where_parts = ["al.payment_status IN ('未收', '部分收款')"]
            params = []
            if search:
                where_parts.append("(al.contract_code ILIKE %s OR al.customer_name ILIKE %s)")
                params.extend([f"%{search}%", f"%{search}%"])
            apply_accounting_period_filter(where_parts, params, "al.accounting_period", accounting_period)
            cur.execute(f"""
                SELECT
                    al.id,
                    '租賃' AS type,
                    al.contract_code,
                    al.customer_code,
                    al.customer_name,
                    al.start_date AS date,
                    al.end_date,
                    al.total_rent AS untaxed_original_amount,
                    al.adjusted_amount AS untaxed_adjusted_amount,
                    al.fee,
                    al.received_amount,
                    al.payment_status,
                    COALESCE(al.accounting_period, 'current') AS accounting_period,
                    COALESCE(cl.needs_invoice, FALSE) AS needs_invoice
                FROM ar_leasing al
                LEFT JOIN contracts_leasing cl ON cl.contract_code = al.contract_code
                WHERE {" AND ".join(where_parts)}
                ORDER BY al.contract_code, al.start_date
            """, tuple(params))
            result.extend(cur.fetchall())

        if not type or type == "買斷":
            where_parts = ["ab.payment_status IN ('未收', '部分收款')"]
            params = []
            if search:
                where_parts.append("(ab.contract_code ILIKE %s OR ab.customer_name ILIKE %s)")
                params.extend([f"%{search}%", f"%{search}%"])
            apply_accounting_period_filter(where_parts, params, "ab.accounting_period", accounting_period)
            cur.execute(f"""
                SELECT
                    ab.id,
                    '買斷' AS type,
                    ab.contract_code,
                    ab.customer_code,
                    ab.customer_name,
                    ab.deal_date AS date,
                    NULL AS end_date,
                    ab.total_amount AS untaxed_original_amount,
                    ab.adjusted_amount AS untaxed_adjusted_amount,
                    ab.fee,
                    ab.received_amount,
                    ab.payment_status,
                    COALESCE(ab.accounting_period, 'current') AS accounting_period,
                    COALESCE(cb.needs_invoice, FALSE) AS needs_invoice
                FROM ar_buyout ab
                LEFT JOIN contracts_buyout cb ON cb.contract_code = ab.contract_code
                WHERE {" AND ".join(where_parts)}
                ORDER BY ab.contract_code, ab.deal_date
            """, tuple(params))
            result.extend(cur.fetchall())

    columns = [
        "id", "type", "contract_code", "customer_code", "customer_name",
        "date", "end_date", "untaxed_original_amount", "untaxed_adjusted_amount",
        "fee", "received_amount", "payment_status", "accounting_period",
        "needs_invoice",
    ]
    serialized = []
    for row in result:
        item = dict(zip(columns, row))
        item["date"] = item["date"].strftime("%Y-%m-%d") if item["date"] else None
        item["end_date"] = item["end_date"].strftime("%Y-%m-%d") if item["end_date"] else None
        needs_invoice = bool(item["needs_invoice"])
        untaxed_original_amount = _to_float(item["untaxed_original_amount"])
        untaxed_adjusted_amount = (
            _to_float(item["untaxed_adjusted_amount"])
            if item["untaxed_adjusted_amount"] is not None
            else None
        )
        untaxed_effective_amount = (
            untaxed_adjusted_amount
            if untaxed_adjusted_amount is not None
            else untaxed_original_amount
        )
        item["needs_invoice"] = needs_invoice
        item["untaxed_original_amount"] = _round_money(untaxed_original_amount)
        item["untaxed_adjusted_amount"] = (
            _round_money(untaxed_adjusted_amount)
            if untaxed_adjusted_amount is not None
            else None
        )
        item["original_amount"] = _round_money(apply_invoice_tax(untaxed_original_amount, needs_invoice))
        item["adjusted_amount"] = (
            _round_money(apply_invoice_tax(untaxed_adjusted_amount, needs_invoice))
            if untaxed_adjusted_amount is not None
            else None
        )
        item["amount"] = _round_money(apply_invoice_tax(untaxed_effective_amount, needs_invoice))
        item["tax_amount"] = _round_money(invoice_tax_amount(untaxed_effective_amount, needs_invoice))
        item["fee"] = _to_float(item["fee"])
        item["received_amount"] = _to_float(item["received_amount"])
        item["unpaid_amount"] = _round_money(max(item["amount"] + item["fee"] - item["received_amount"], 0.0))
        serialized.append(item)
    return serialized


@router.get("/reconcilable/service-expenses")
def get_reconcilable_service_expenses(
    search: Optional[str] = Query(None, description="搜尋關鍵字"),
    service_type: Optional[str] = Query(None, description="服務類型"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    where_parts = ["se.payment_status IN ('未收', '部分收款')"]
    params = []

    if search:
        where_parts.append("""
            (
                COALESCE(se.contract_code, '') ILIKE %s
                OR COALESCE(se.customer_name, '') ILIKE %s
                OR COALESCE(se.expense_description, '') ILIKE %s
                OR COALESCE(se.vendor_name, '') ILIKE %s
                OR COALESCE(se.repair_company_code, '') ILIKE %s
                OR COALESCE(company.name, '') ILIKE %s
            )
        """)
        params.extend([f"%{search}%"] * 6)

    if service_type:
        where_parts.append("""
            (
                se.service_type ILIKE %s
                OR COALESCE(se.expense_category, '') ILIKE %s
            )
        """)
        params.extend([f"%{service_type}%", f"%{service_type}%"])
    apply_accounting_period_filter(where_parts, params, "se.accounting_period", accounting_period)

    where_clause = " WHERE " + " AND ".join(where_parts)

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT
                se.id,
                se.contract_code,
                se.customer_code,
                se.customer_name,
                se.service_date,
                se.service_type,
                COALESCE(se.repair_company_code, se.vendor_name) AS vendor,
                COALESCE(NULLIF(se.repair_company_code, ''), NULLIF(se.vendor_name, ''), '') AS payee_code,
                COALESCE(
                    NULLIF(company.name, ''),
                    NULLIF(se.vendor_name, ''),
                    NULLIF(se.repair_company_code, ''),
                    '未指定付款對象'
                ) AS payee_name,
                se.total_amount AS original_amount,
                se.adjusted_amount,
                COALESCE(se.adjusted_amount, se.total_amount) AS amount,
                COALESCE(se.paid_amount, 0) AS paid_amount,
                GREATEST(COALESCE(se.adjusted_amount, se.total_amount) - COALESCE(se.paid_amount, 0), 0) AS unpaid_amount,
                se.payment_status,
                COALESCE(se.expense_source, 'contract') AS expense_source,
                COALESCE(NULLIF(se.expense_category, ''), se.service_type) AS expense_category,
                se.expense_description,
                COALESCE(se.accounting_period, 'current') AS accounting_period
            FROM service_expense se
            LEFT JOIN companies company ON company.company_code = se.repair_company_code
            {where_clause}
            ORDER BY COALESCE(se.service_date, se.created_at::date) DESC, se.id DESC
        """, tuple(params))
        rows = cur.fetchall()

    columns = [
        "id", "contract_code", "customer_code", "customer_name", "service_date",
        "service_type", "vendor", "payee_code", "payee_name", "original_amount",
        "adjusted_amount", "amount", "paid_amount", "unpaid_amount",
        "payment_status", "expense_source", "expense_category", "expense_description",
        "accounting_period",
    ]
    result = []
    for row in rows:
        item = dict(zip(columns, row))
        item["service_date"] = item["service_date"].strftime("%Y-%m-%d") if item["service_date"] else None
        item["original_amount"] = _to_float(item["original_amount"])
        item["adjusted_amount"] = _to_float(item["adjusted_amount"]) if item["adjusted_amount"] is not None else None
        item["amount"] = _to_float(item["amount"])
        item["paid_amount"] = _to_float(item["paid_amount"])
        item["unpaid_amount"] = _to_float(item["unpaid_amount"])
        item["payment_status"] = _service_status_to_display(item["payment_status"])
        result.append(item)
    return result


def _build_lines(request: ReconcileRequest, ledger_amount: float) -> List[dict]:
    lines: List[dict] = []

    if request.lines:
        for item in request.lines:
            lines.append({
                "target_id": item.target_id,
                "allocated_amount": _to_float(item.allocated_amount),
                "fee_amount": _to_float(item.fee_amount),
                "ar_type": _normalize_ar_type(item.ar_type),
            })
    elif request.reconcile_type == "receivable" and request.ar_id:
        lines.append({
            "target_id": request.ar_id,
            "allocated_amount": ledger_amount,
            "fee_amount": _to_float(request.fee_amount),
            "ar_type": _normalize_ar_type(request.ar_type),
        })
    elif request.reconcile_type == "service_expense" and request.service_expense_id:
        lines.append({
            "target_id": request.service_expense_id,
            "allocated_amount": ledger_amount,
            "fee_amount": 0.0,
            "ar_type": None,
        })

    if not lines:
        raise HTTPException(status_code=400, detail="請至少提供一筆對帳明細")

    seen_keys = set()
    total_ledger_usage = 0.0
    for item in lines:
        if item["allocated_amount"] <= 0:
            raise HTTPException(status_code=400, detail="分攤金額需大於 0")
        if item["fee_amount"] < 0:
            raise HTTPException(status_code=400, detail="手續費不可為負數")
        key = (request.reconcile_type, item["target_id"], item["ar_type"])
        if key in seen_keys:
            raise HTTPException(status_code=400, detail="同一筆對帳資料不可重複分攤")
        seen_keys.add(key)
        total_ledger_usage += item["allocated_amount"]
        if request.reconcile_type == "service_expense":
            total_ledger_usage += item["fee_amount"]

    if total_ledger_usage > ledger_amount + 0.000001:
        raise HTTPException(status_code=400, detail="分攤金額與手續費加總不可超過銀行流水金額")

    return lines


@router.post("/{id}/reconcile", response_model=dict)
def reconcile_bank_ledger(id: int, request: ReconcileRequest):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, income, expense, is_reconciled
                FROM bank_ledger
                WHERE id = %s
                FOR UPDATE
            """, (id,))
            ledger_row = cur.fetchone()
            if not ledger_row:
                raise HTTPException(status_code=404, detail="銀行帳本資料不存在")

            _, income, expense, is_reconciled = ledger_row
            income = _to_float(income)
            expense = _to_float(expense)

            cur.execute("""
                SELECT COUNT(*)
                FROM bank_ledger_reconciliation_lines
                WHERE bank_ledger_id = %s
            """, (id,))
            existing_line_count = cur.fetchone()[0]

            if is_reconciled or existing_line_count:
                raise HTTPException(status_code=400, detail="這筆銀行流水已完成對帳")

            if request.reconcile_type == "receivable":
                if income <= 0:
                    raise HTTPException(status_code=400, detail="收入流水才能對應應收帳款")
                lines = _build_lines(request, income)
            elif request.reconcile_type == "service_expense":
                if expense <= 0:
                    raise HTTPException(status_code=400, detail="支出流水才能對應服務費用")
                lines = _build_lines(request, expense)
            else:
                raise HTTPException(status_code=400, detail="對帳類型錯誤")

            for item in lines:
                if request.reconcile_type == "receivable":
                    normalized_ar_type = item["ar_type"]
                    if normalized_ar_type == "租賃":
                        cur.execute("""
                            SELECT ar.total_rent, ar.adjusted_amount, ar.fee, ar.received_amount,
                                   COALESCE(cl.needs_invoice, FALSE) AS needs_invoice
                            FROM ar_leasing ar
                            LEFT JOIN contracts_leasing cl ON cl.contract_code = ar.contract_code
                            WHERE ar.id = %s
                            FOR UPDATE OF ar
                        """, (item["target_id"],))
                    elif normalized_ar_type == "買斷":
                        cur.execute("""
                            SELECT ar.total_amount, ar.adjusted_amount, ar.fee, ar.received_amount,
                                   COALESCE(cb.needs_invoice, FALSE) AS needs_invoice
                            FROM ar_buyout ar
                            LEFT JOIN contracts_buyout cb ON cb.contract_code = ar.contract_code
                            WHERE ar.id = %s
                            FOR UPDATE OF ar
                        """, (item["target_id"],))
                    else:
                        raise HTTPException(status_code=400, detail="應收帳款類型錯誤")

                    ar_row = cur.fetchone()
                    if not ar_row:
                        raise HTTPException(status_code=404, detail="應收帳款不存在")

                    base_amount = _to_float(ar_row[0])
                    adjusted_amount = _to_float(ar_row[1]) if ar_row[1] is not None else None
                    fee = _to_float(ar_row[2])
                    received_amount = _to_float(ar_row[3])
                    needs_invoice = bool(ar_row[4])
                    effective_untaxed_amount = adjusted_amount if adjusted_amount is not None else base_amount
                    effective_amount = apply_invoice_tax(effective_untaxed_amount, needs_invoice)
                    outstanding_after_fee = effective_amount + fee + item["fee_amount"] - received_amount

                    if item["allocated_amount"] > outstanding_after_fee + 0.000001:
                        raise HTTPException(status_code=400, detail="分攤金額不可超過該筆應收未收金額")

                    new_fee = fee + item["fee_amount"]
                    new_received = received_amount + item["allocated_amount"]
                    new_status = _calculate_receivable_status(
                        effective_untaxed_amount,
                        new_fee,
                        new_received,
                        needs_invoice,
                    )

                    if request.auto_update:
                        if normalized_ar_type == "租賃":
                            cur.execute("""
                                UPDATE ar_leasing
                                SET fee = %s,
                                    received_amount = %s,
                                    payment_status = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (new_fee, new_received, new_status, item["target_id"]))
                        else:
                            cur.execute("""
                                UPDATE ar_buyout
                                SET fee = %s,
                                    received_amount = %s,
                                    payment_status = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (new_fee, new_received, new_status, item["target_id"]))

                else:
                    cur.execute("""
                        SELECT total_amount, adjusted_amount, paid_amount
                        FROM service_expense
                        WHERE id = %s
                        FOR UPDATE
                    """, (item["target_id"],))
                    se_row = cur.fetchone()
                    if not se_row:
                        raise HTTPException(status_code=404, detail="服務費用不存在")

                    base_amount = _to_float(se_row[0])
                    adjusted_amount = _to_float(se_row[1]) if se_row[1] is not None else None
                    paid_amount = _to_float(se_row[2])
                    effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
                    outstanding_amount = effective_amount - paid_amount

                    if item["allocated_amount"] > outstanding_amount + 0.000001:
                        raise HTTPException(status_code=400, detail="分攤金額不可超過該筆支出未付金額")

                    new_paid = paid_amount + item["allocated_amount"]
                    new_status = _calculate_service_status(effective_amount, new_paid)

                    if request.auto_update:
                        cur.execute("""
                            UPDATE service_expense
                            SET paid_amount = %s,
                                payment_status = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (new_paid, new_status, item["target_id"]))

                cur.execute("""
                    INSERT INTO bank_ledger_reconciliation_lines
                    (bank_ledger_id, target_type, target_id, ar_type, allocated_amount, fee_amount)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    id,
                    request.reconcile_type,
                    item["target_id"],
                    item["ar_type"],
                    item["allocated_amount"],
                    item["fee_amount"],
                ))

            first_line = lines[0]
            if request.reconcile_type == "receivable" and len(lines) == 1:
                reconciled_ar_id = first_line["target_id"]
                reconciled_ar_type = first_line["ar_type"]
                reconciled_service_expense_id = None
            elif request.reconcile_type == "service_expense" and len(lines) == 1:
                reconciled_ar_id = None
                reconciled_ar_type = None
                reconciled_service_expense_id = first_line["target_id"]
            else:
                reconciled_ar_id = None
                reconciled_ar_type = None
                reconciled_service_expense_id = None

            cur.execute("""
                UPDATE bank_ledger
                SET is_reconciled = true,
                    reconciled_ar_id = %s,
                    reconciled_ar_type = %s,
                    reconciled_service_expense_id = %s,
                    reconciled_payable_contract_code = NULL,
                    reconciled_payable_type = NULL,
                    reconciled_fee_amount = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                reconciled_ar_id,
                reconciled_ar_type,
                reconciled_service_expense_id,
                sum(item["fee_amount"] for item in lines),
                id,
            ))

            conn.commit()
            return _fetch_ledger_detail(cur, id)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


def _revert_legacy_reconciliation(cur, ledger_id: int, income: float, expense: float,
                                  ar_id: Optional[int], ar_type: Optional[str],
                                  service_expense_id: Optional[int], reconciled_fee_amount: float,
                                  revert: bool):
    normalized_ar_type = _normalize_ar_type(ar_type)

    if ar_id and normalized_ar_type:
        if revert:
            if normalized_ar_type == "租賃":
                cur.execute("""
                    SELECT ar.total_rent, ar.adjusted_amount, ar.fee, ar.received_amount,
                           COALESCE(cl.needs_invoice, FALSE) AS needs_invoice
                    FROM ar_leasing ar
                    LEFT JOIN contracts_leasing cl ON cl.contract_code = ar.contract_code
                    WHERE ar.id = %s
                    FOR UPDATE OF ar
                """, (ar_id,))
            else:
                cur.execute("""
                    SELECT ar.total_amount, ar.adjusted_amount, ar.fee, ar.received_amount,
                           COALESCE(cb.needs_invoice, FALSE) AS needs_invoice
                    FROM ar_buyout ar
                    LEFT JOIN contracts_buyout cb ON cb.contract_code = ar.contract_code
                    WHERE ar.id = %s
                    FOR UPDATE OF ar
                """, (ar_id,))

            ar_row = cur.fetchone()
            if ar_row:
                base_amount = _to_float(ar_row[0])
                adjusted_amount = _to_float(ar_row[1]) if ar_row[1] is not None else None
                fee = _to_float(ar_row[2])
                received_amount = _to_float(ar_row[3])
                needs_invoice = bool(ar_row[4])
                effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
                new_fee = max(0.0, fee - reconciled_fee_amount)
                new_received = max(0.0, received_amount - income)
                new_status = _calculate_receivable_status(effective_amount, new_fee, new_received, needs_invoice)

                if normalized_ar_type == "租賃":
                    cur.execute("""
                        UPDATE ar_leasing
                        SET fee = %s,
                            received_amount = %s,
                            payment_status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (new_fee, new_received, new_status, ar_id))
                else:
                    cur.execute("""
                        UPDATE ar_buyout
                        SET fee = %s,
                            received_amount = %s,
                            payment_status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (new_fee, new_received, new_status, ar_id))

    elif service_expense_id:
        if revert:
            cur.execute("""
                SELECT total_amount, adjusted_amount, paid_amount
                FROM service_expense
                WHERE id = %s
                FOR UPDATE
            """, (service_expense_id,))
            se_row = cur.fetchone()
            if se_row:
                base_amount = _to_float(se_row[0])
                adjusted_amount = _to_float(se_row[1]) if se_row[1] is not None else None
                paid_amount = _to_float(se_row[2])
                effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
                new_paid = max(0.0, paid_amount - expense)
                new_status = _calculate_service_status(effective_amount, new_paid)
                cur.execute("""
                    UPDATE service_expense
                    SET paid_amount = %s,
                        payment_status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (new_paid, new_status, service_expense_id))

    cur.execute("""
        UPDATE bank_ledger
        SET is_reconciled = false,
            reconciled_ar_id = NULL,
            reconciled_ar_type = NULL,
            reconciled_payable_contract_code = NULL,
            reconciled_payable_type = NULL,
            reconciled_service_expense_id = NULL,
            reconciled_fee_amount = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (ledger_id,))


@router.post("/{id}/unreconcile", response_model=dict)
def unreconcile_bank_ledger(
    id: int,
    revert: bool = Query(True, description="是否還原應收/應付帳款"),
):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, income, expense, is_reconciled,
                       reconciled_ar_id, reconciled_ar_type,
                       reconciled_service_expense_id, reconciled_fee_amount
                FROM bank_ledger
                WHERE id = %s
                FOR UPDATE
            """, (id,))
            ledger_row = cur.fetchone()
            if not ledger_row:
                raise HTTPException(status_code=404, detail="銀行帳本資料不存在")

            ledger_id, income, expense, is_reconciled, ar_id, ar_type, se_id, reconciled_fee_amount = ledger_row
            income = _to_float(income)
            expense = _to_float(expense)
            reconciled_fee_amount = _to_float(reconciled_fee_amount)

            cur.execute("""
                SELECT id, target_type, target_id, ar_type, allocated_amount, fee_amount
                FROM bank_ledger_reconciliation_lines
                WHERE bank_ledger_id = %s
                ORDER BY id
            """, (id,))
            lines = cur.fetchall()

            if not is_reconciled and not lines:
                raise HTTPException(status_code=400, detail="這筆銀行流水尚未對帳")

            if lines:
                if revert:
                    for _, target_type, target_id, line_ar_type, allocated_amount, fee_amount in lines:
                        allocated_amount = _to_float(allocated_amount)
                        fee_amount = _to_float(fee_amount)

                        if target_type == "receivable":
                            normalized_ar_type = _normalize_ar_type(line_ar_type)
                            if normalized_ar_type == "租賃":
                                cur.execute("""
                                    SELECT ar.total_rent, ar.adjusted_amount, ar.fee, ar.received_amount,
                                           COALESCE(cl.needs_invoice, FALSE) AS needs_invoice
                                    FROM ar_leasing ar
                                    LEFT JOIN contracts_leasing cl ON cl.contract_code = ar.contract_code
                                    WHERE ar.id = %s
                                    FOR UPDATE OF ar
                                """, (target_id,))
                            else:
                                cur.execute("""
                                    SELECT ar.total_amount, ar.adjusted_amount, ar.fee, ar.received_amount,
                                           COALESCE(cb.needs_invoice, FALSE) AS needs_invoice
                                    FROM ar_buyout ar
                                    LEFT JOIN contracts_buyout cb ON cb.contract_code = ar.contract_code
                                    WHERE ar.id = %s
                                    FOR UPDATE OF ar
                                """, (target_id,))

                            ar_row = cur.fetchone()
                            if not ar_row:
                                continue

                            base_amount = _to_float(ar_row[0])
                            adjusted_amount = _to_float(ar_row[1]) if ar_row[1] is not None else None
                            fee = _to_float(ar_row[2])
                            received_amount = _to_float(ar_row[3])
                            needs_invoice = bool(ar_row[4])
                            effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
                            new_fee = max(0.0, fee - fee_amount)
                            new_received = max(0.0, received_amount - allocated_amount)
                            new_status = _calculate_receivable_status(effective_amount, new_fee, new_received, needs_invoice)

                            if normalized_ar_type == "租賃":
                                cur.execute("""
                                    UPDATE ar_leasing
                                    SET fee = %s,
                                        received_amount = %s,
                                        payment_status = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE id = %s
                                """, (new_fee, new_received, new_status, target_id))
                            else:
                                cur.execute("""
                                    UPDATE ar_buyout
                                    SET fee = %s,
                                        received_amount = %s,
                                        payment_status = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE id = %s
                                """, (new_fee, new_received, new_status, target_id))

                        elif target_type == "service_expense":
                            cur.execute("""
                                SELECT total_amount, adjusted_amount, paid_amount
                                FROM service_expense
                                WHERE id = %s
                                FOR UPDATE
                            """, (target_id,))
                            se_row = cur.fetchone()
                            if not se_row:
                                continue

                            base_amount = _to_float(se_row[0])
                            adjusted_amount = _to_float(se_row[1]) if se_row[1] is not None else None
                            paid_amount = _to_float(se_row[2])
                            effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
                            new_paid = max(0.0, paid_amount - allocated_amount)
                            new_status = _calculate_service_status(effective_amount, new_paid)
                            cur.execute("""
                                UPDATE service_expense
                                SET paid_amount = %s,
                                    payment_status = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (new_paid, new_status, target_id))

                cur.execute("DELETE FROM bank_ledger_reconciliation_lines WHERE bank_ledger_id = %s", (id,))
                cur.execute("""
                    UPDATE bank_ledger
                    SET is_reconciled = false,
                        reconciled_ar_id = NULL,
                        reconciled_ar_type = NULL,
                        reconciled_payable_contract_code = NULL,
                        reconciled_payable_type = NULL,
                        reconciled_service_expense_id = NULL,
                        reconciled_fee_amount = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (id,))
            else:
                _revert_legacy_reconciliation(
                    cur,
                    ledger_id=ledger_id,
                    income=income,
                    expense=expense,
                    ar_id=ar_id,
                    ar_type=ar_type,
                    service_expense_id=se_id,
                    reconciled_fee_amount=reconciled_fee_amount,
                    revert=revert,
                )

            conn.commit()
            return _fetch_ledger_detail(cur, id)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
