"""帳款查詢與維護 API。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.accounting_period import accounting_period_for_date, apply_accounting_period_filter
from app.billing import (
    apply_invoice_tax,
    calculate_receivable_status,
    invoice_tax_amount,
    remove_invoice_tax,
)
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

PAYABLE_STATUS_REVERSE_MAP = {value: key for key, value in PAYABLE_STATUS_MAP.items()}


class AmountUpdate(BaseModel):
    amount: float


class ExtraExpenseCreate(BaseModel):
    service_date: date
    expense_category: Optional[str] = None
    description: str
    amount: float
    contract_code: Optional[str] = None
    vendor_name: Optional[str] = None


def row_to_dict(row, columns):
    return dict(zip(columns, row))


def _to_float(value) -> float:
    return float(value) if value is not None else 0.0


def _round_money(value) -> float:
    return round(_to_float(value), 2)


def _serialize_date(value):
    if not value:
        return None
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)


def _normalize_ar_type(ar_type: str) -> str:
    value = (ar_type or "").strip().lower()
    if value in {"租賃", "租赁", "leasing", "lease"}:
        return "租賃"
    if value in {"買斷", "买断", "buyout"}:
        return "買斷"
    raise HTTPException(status_code=400, detail="應收帳款類型錯誤")


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


def _display_status_to_service(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    return PAYABLE_STATUS_REVERSE_MAP.get(status, status)


def _lookup_contract_context(cur, contract_code: str):
    if not contract_code:
        return None, None, None

    cur.execute("""
        SELECT customer_code, customer_name, '租賃'
        FROM contracts_leasing
        WHERE contract_code = %s
        UNION ALL
        SELECT customer_code, customer_name, '買斷'
        FROM contracts_buyout
        WHERE contract_code = %s
        LIMIT 1
    """, (contract_code, contract_code))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="關聯合約不存在")
    return row[0], row[1], row[2]


@router.get("/receivables")
def get_receivables(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="繳費狀況"),
    type: Optional[str] = Query(None, description="類型（租賃/買斷）"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    with get_cursor() as cur:
        result = []

        if not type or type == "租賃":
            where_parts = []
            params = []
            if contract_code:
                where_parts.append("al.contract_code ILIKE %s")
                params.append(f"%{contract_code}%")
            if customer_code:
                where_parts.append("al.customer_code ILIKE %s")
                params.append(f"%{customer_code}%")
            if customer_name:
                where_parts.append("al.customer_name ILIKE %s")
                params.append(f"%{customer_name}%")
            if from_date:
                where_parts.append("al.start_date >= %s")
                params.append(from_date)
            if to_date:
                where_parts.append("al.start_date <= %s")
                params.append(to_date)
            if payment_status:
                where_parts.append("al.payment_status = %s")
                params.append(payment_status)
            apply_accounting_period_filter(where_parts, params, "al.accounting_period", accounting_period)

            where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
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
                {where_clause}
                ORDER BY al.contract_code, al.start_date
            """, tuple(params))
            result.extend(cur.fetchall())

        if not type or type == "買斷":
            where_parts = []
            params = []
            if contract_code:
                where_parts.append("ab.contract_code ILIKE %s")
                params.append(f"%{contract_code}%")
            if customer_code:
                where_parts.append("ab.customer_code ILIKE %s")
                params.append(f"%{customer_code}%")
            if customer_name:
                where_parts.append("ab.customer_name ILIKE %s")
                params.append(f"%{customer_name}%")
            if from_date:
                where_parts.append("ab.deal_date >= %s")
                params.append(from_date)
            if to_date:
                where_parts.append("ab.deal_date <= %s")
                params.append(to_date)
            if payment_status:
                where_parts.append("ab.payment_status = %s")
                params.append(payment_status)
            apply_accounting_period_filter(where_parts, params, "ab.accounting_period", accounting_period)

            where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
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
                {where_clause}
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
        item = row_to_dict(row, columns)
        item["date"] = _serialize_date(item["date"])
        item["end_date"] = _serialize_date(item["end_date"])
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
        serialized.append(item)

    return serialized


def _get_payables(status_mode: str,
                  contract_code: Optional[str] = None,
                  customer_code: Optional[str] = None,
                  customer_name: Optional[str] = None,
                  from_date: Optional[str] = None,
                  to_date: Optional[str] = None,
                  payment_status: Optional[str] = None,
                  payable_type: Optional[str] = None,
                  contract_type: Optional[str] = None,
                  accounting_period: Optional[str] = "current"):
    date_expr = "COALESCE(se.service_date, cl.start_date, cb.deal_date)"
    contract_type_expr = """
        CASE
            WHEN cl.contract_code IS NOT NULL THEN '租賃'
            WHEN cb.contract_code IS NOT NULL THEN '買斷'
            WHEN COALESCE(se.expense_source, 'contract') = 'extra' THEN '額外開銷'
            ELSE ''
        END
    """
    payable_type_expr = """
        CASE
            WHEN COALESCE(se.expense_source, 'contract') = 'extra'
                THEN COALESCE(NULLIF(se.expense_category, ''), '額外開銷')
            ELSE se.service_type
        END
    """
    effective_amount_expr = "COALESCE(se.adjusted_amount, se.total_amount)"
    company_expr = "COALESCE(NULLIF(se.repair_company_code, ''), NULLIF(se.vendor_name, ''), '')"
    payee_name_expr = """
        COALESCE(
            NULLIF(company.name, ''),
            NULLIF(se.vendor_name, ''),
            NULLIF(se.repair_company_code, ''),
            '未指定付款對象'
        )
    """

    where_parts = []
    params = []

    if status_mode == "unpaid":
        where_parts.append("se.payment_status IN ('未收', '部分收款')")
    else:
        where_parts.append("se.payment_status = '已收款'")

    if contract_code:
        where_parts.append("COALESCE(se.contract_code, '') ILIKE %s")
        params.append(f"%{contract_code}%")
    if customer_code:
        where_parts.append("COALESCE(se.customer_code, '') ILIKE %s")
        params.append(f"%{customer_code}%")
    if customer_name:
        where_parts.append("COALESCE(se.customer_name, '') ILIKE %s")
        params.append(f"%{customer_name}%")
    if from_date:
        where_parts.append(f"{date_expr} >= %s")
        params.append(from_date)
    if to_date:
        where_parts.append(f"{date_expr} <= %s")
        params.append(to_date)
    if payment_status:
        where_parts.append("se.payment_status = %s")
        params.append(_display_status_to_service(payment_status))
    if payable_type:
        where_parts.append(f"{payable_type_expr} ILIKE %s")
        params.append(f"%{payable_type}%")
    if contract_type:
        where_parts.append(f"{contract_type_expr} = %s")
        params.append(contract_type)
    apply_accounting_period_filter(where_parts, params, "se.accounting_period", accounting_period)

    where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT
                se.id,
                se.contract_code,
                {contract_type_expr} AS contract_type,
                se.customer_code,
                se.customer_name,
                {date_expr} AS date,
                {payable_type_expr} AS payable_type,
                {company_expr} AS company_code,
                {payee_name_expr} AS payee_name,
                se.vendor_name,
                se.expense_category,
                se.service_type,
                se.total_amount AS original_amount,
                se.adjusted_amount,
                {effective_amount_expr} AS amount,
                COALESCE(se.paid_amount, 0) AS paid_amount,
                GREATEST({effective_amount_expr} - COALESCE(se.paid_amount, 0), 0) AS unpaid_amount,
                se.payment_status,
                COALESCE(se.expense_source, 'contract') AS expense_source,
                se.expense_description AS description,
                COALESCE(se.accounting_period, 'current') AS accounting_period
            FROM service_expense se
            LEFT JOIN contracts_leasing cl ON cl.contract_code = se.contract_code
            LEFT JOIN contracts_buyout cb ON cb.contract_code = se.contract_code
            LEFT JOIN companies company ON company.company_code = se.repair_company_code
            {where_clause}
            ORDER BY {date_expr} DESC NULLS LAST, se.id DESC
        """, tuple(params))
        rows = cur.fetchall()

    columns = [
        "id", "contract_code", "contract_type", "customer_code", "customer_name",
        "date", "payable_type", "company_code", "payee_name", "vendor_name",
        "expense_category", "service_type", "original_amount", "adjusted_amount",
        "amount", "paid_amount", "unpaid_amount", "payment_status", "expense_source",
        "description", "accounting_period",
    ]

    result = []
    for row in rows:
        item = row_to_dict(row, columns)
        item["date"] = _serialize_date(item["date"])
        item["original_amount"] = _to_float(item["original_amount"])
        item["adjusted_amount"] = _to_float(item["adjusted_amount"]) if item["adjusted_amount"] is not None else None
        item["amount"] = _to_float(item["amount"])
        item["paid_amount"] = _to_float(item["paid_amount"])
        item["unpaid_amount"] = _to_float(item["unpaid_amount"])
        item["payment_status"] = _service_status_to_display(item["payment_status"])
        result.append(item)

    return result


@router.get("/payables/unpaid")
def get_unpaid_payables(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="付款狀況"),
    payable_type: Optional[str] = Query(None, description="應付類型"),
    contract_type: Optional[str] = Query(None, description="合約類型"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    return _get_payables(
        "unpaid",
        contract_code=contract_code,
        customer_code=customer_code,
        customer_name=customer_name,
        from_date=from_date,
        to_date=to_date,
        payment_status=payment_status,
        payable_type=payable_type,
        contract_type=contract_type,
        accounting_period=accounting_period,
    )


@router.get("/payables/paid")
def get_paid_payables(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="付款狀況"),
    payable_type: Optional[str] = Query(None, description="應付類型"),
    contract_type: Optional[str] = Query(None, description="合約類型"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    return _get_payables(
        "paid",
        contract_code=contract_code,
        customer_code=customer_code,
        customer_name=customer_name,
        from_date=from_date,
        to_date=to_date,
        payment_status=payment_status,
        payable_type=payable_type,
        contract_type=contract_type,
        accounting_period=accounting_period,
    )


@router.get("/service")
def get_service_expenses(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="付款狀況"),
    service_type: Optional[str] = Query(None, description="服務類型"),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    where_parts = ["COALESCE(expense_source, 'contract') = 'contract'"]
    params = []

    if contract_code:
        where_parts.append("contract_code ILIKE %s")
        params.append(f"%{contract_code}%")
    if customer_code:
        where_parts.append("customer_code ILIKE %s")
        params.append(f"%{customer_code}%")
    if customer_name:
        where_parts.append("customer_name ILIKE %s")
        params.append(f"%{customer_name}%")
    if from_date:
        where_parts.append("COALESCE(service_date, created_at::date) >= %s")
        params.append(from_date)
    if to_date:
        where_parts.append("COALESCE(service_date, created_at::date) <= %s")
        params.append(to_date)
    if payment_status:
        where_parts.append("payment_status = %s")
        params.append(_display_status_to_service(payment_status))
    if service_type:
        where_parts.append("service_type ILIKE %s")
        params.append(f"%{service_type}%")
    apply_accounting_period_filter(where_parts, params, "accounting_period", accounting_period)

    where_clause = " WHERE " + " AND ".join(where_parts)

    with get_cursor() as cur:
        cur.execute(f"""
            SELECT
                id,
                contract_code,
                customer_code,
                customer_name,
                service_date,
                confirm_date,
                service_type,
                repair_company_code,
                total_amount AS original_amount,
                adjusted_amount,
                COALESCE(adjusted_amount, total_amount) AS amount,
                COALESCE(paid_amount, 0) AS paid_amount,
                payment_status,
                COALESCE(accounting_period, 'current') AS accounting_period
            FROM service_expense
            {where_clause}
            ORDER BY COALESCE(service_date, created_at::date) DESC, id DESC
        """, tuple(params))
        rows = cur.fetchall()

    columns = [
        "id", "contract_code", "customer_code", "customer_name",
        "service_date", "confirm_date", "service_type", "repair_company_code",
        "original_amount", "adjusted_amount", "amount", "paid_amount",
        "payment_status", "accounting_period",
    ]

    result = []
    for row in rows:
        item = row_to_dict(row, columns)
        item["service_date"] = _serialize_date(item["service_date"])
        item["confirm_date"] = _serialize_date(item["confirm_date"])
        item["original_amount"] = _to_float(item["original_amount"])
        item["adjusted_amount"] = _to_float(item["adjusted_amount"]) if item["adjusted_amount"] is not None else None
        item["amount"] = _to_float(item["amount"])
        item["paid_amount"] = _to_float(item["paid_amount"])
        item["payment_status"] = _service_status_to_display(item["payment_status"])
        result.append(item)

    return result


@router.put("/receivables/{ar_type}/{ar_id}/amount")
def update_receivable_amount(ar_type: str, ar_id: int, payload: AmountUpdate):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="金額需大於 0")

    normalized_type = _normalize_ar_type(ar_type)
    table_name = "ar_leasing" if normalized_type == "租賃" else "ar_buyout"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if normalized_type == "租賃":
                cur.execute("""
                    SELECT ar.total_rent, ar.fee, ar.received_amount,
                           COALESCE(cl.needs_invoice, FALSE) AS needs_invoice
                    FROM ar_leasing ar
                    LEFT JOIN contracts_leasing cl ON cl.contract_code = ar.contract_code
                    WHERE ar.id = %s
                    FOR UPDATE OF ar
                """, (ar_id,))
            else:
                cur.execute("""
                    SELECT ar.total_amount, ar.fee, ar.received_amount,
                           COALESCE(cb.needs_invoice, FALSE) AS needs_invoice
                    FROM ar_buyout ar
                    LEFT JOIN contracts_buyout cb ON cb.contract_code = ar.contract_code
                    WHERE ar.id = %s
                    FOR UPDATE OF ar
                """, (ar_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="應收帳款不存在")

            original_amount = _to_float(row[0])
            fee = _to_float(row[1])
            received_amount = _to_float(row[2])
            needs_invoice = bool(row[3])
            adjusted_untaxed_amount = _round_money(remove_invoice_tax(payload.amount, needs_invoice))
            adjusted_amount = (
                None
                if abs(adjusted_untaxed_amount - original_amount) < 0.000001
                else adjusted_untaxed_amount
            )
            effective_untaxed_amount = adjusted_amount if adjusted_amount is not None else original_amount
            payment_status = calculate_receivable_status(
                effective_untaxed_amount,
                fee,
                received_amount,
                needs_invoice,
            )

            cur.execute(f"""
                UPDATE {table_name}
                SET adjusted_amount = %s,
                    payment_status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (adjusted_amount, payment_status, ar_id))
            conn.commit()

            return {
                "id": ar_id,
                "type": normalized_type,
                "original_amount": _round_money(apply_invoice_tax(original_amount, needs_invoice)),
                "adjusted_amount": (
                    _round_money(apply_invoice_tax(adjusted_amount, needs_invoice))
                    if adjusted_amount is not None
                    else None
                ),
                "amount": _round_money(apply_invoice_tax(effective_untaxed_amount, needs_invoice)),
                "untaxed_original_amount": _round_money(original_amount),
                "untaxed_adjusted_amount": _round_money(adjusted_amount) if adjusted_amount is not None else None,
                "tax_amount": _round_money(invoice_tax_amount(effective_untaxed_amount, needs_invoice)),
                "needs_invoice": needs_invoice,
                "fee": fee,
                "received_amount": received_amount,
                "payment_status": payment_status,
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.put("/service/{expense_id}/amount")
def update_service_expense_amount(expense_id: int, payload: AmountUpdate):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="金額需大於 0")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT total_amount, paid_amount
                FROM service_expense
                WHERE id = %s
                FOR UPDATE
            """, (expense_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="服務費用不存在")

            original_amount = _to_float(row[0])
            paid_amount = _to_float(row[1])
            adjusted_amount = None if abs(payload.amount - original_amount) < 0.000001 else payload.amount
            payment_status = _calculate_service_status(payload.amount, paid_amount)

            cur.execute("""
                UPDATE service_expense
                SET adjusted_amount = %s,
                    payment_status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (adjusted_amount, payment_status, expense_id))
            conn.commit()

            return {
                "id": expense_id,
                "original_amount": original_amount,
                "adjusted_amount": adjusted_amount,
                "amount": payload.amount,
                "paid_amount": paid_amount,
                "payment_status": _service_status_to_display(payment_status),
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.post("/service/extra", status_code=201)
def create_extra_expense(payload: ExtraExpenseCreate):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="金額需大於 0")
    if not payload.description or not payload.description.strip():
        raise HTTPException(status_code=400, detail="請填寫額外開銷內容")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            customer_code, customer_name, _ = _lookup_contract_context(cur, payload.contract_code) if payload.contract_code else (None, None, None)
            category = (payload.expense_category or "額外開銷").strip() or "額外開銷"
            service_type = category[:100]
            description = payload.description.strip()
            vendor_name = payload.vendor_name.strip() if payload.vendor_name else None
            accounting_period = accounting_period_for_date(payload.service_date)

            cur.execute("""
                INSERT INTO service_expense
                (contract_code, customer_code, customer_name, service_date, service_type,
                 total_amount, adjusted_amount, paid_amount, payment_status, expense_source,
                 expense_category, expense_description, vendor_name, accounting_period)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, 0, '未收', 'extra', %s, %s, %s, %s)
                RETURNING id, contract_code, customer_code, customer_name, service_date,
                          service_type, total_amount, adjusted_amount, paid_amount,
                          payment_status, expense_source, expense_category,
                          expense_description, vendor_name, accounting_period
            """, (
                payload.contract_code,
                customer_code,
                customer_name,
                payload.service_date,
                service_type,
                payload.amount,
                category,
                description,
                vendor_name,
                accounting_period,
            ))
            row = cur.fetchone()
            conn.commit()

            return {
                "id": row[0],
                "contract_code": row[1],
                "customer_code": row[2],
                "customer_name": row[3],
                "service_date": _serialize_date(row[4]),
                "service_type": row[5],
                "original_amount": _to_float(row[6]),
                "adjusted_amount": _to_float(row[7]) if row[7] is not None else None,
                "amount": _to_float(row[7]) if row[7] is not None else _to_float(row[6]),
                "paid_amount": _to_float(row[8]),
                "payment_status": _service_status_to_display(row[9]),
                "expense_source": row[10],
                "expense_category": row[11],
                "description": row[12],
                "vendor_name": row[13],
                "accounting_period": row[14],
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.put("/service/extra/{expense_id}")
def update_extra_expense(expense_id: int, payload: ExtraExpenseCreate):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="金額需大於 0")
    if not payload.description or not payload.description.strip():
        raise HTTPException(status_code=400, detail="請填寫額外開銷內容")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(expense_source, 'contract'), COALESCE(paid_amount, 0)
                FROM service_expense
                WHERE id = %s
                FOR UPDATE
            """, (expense_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="額外開銷不存在")
            if existing[0] != "extra":
                raise HTTPException(status_code=400, detail="合約自動產生的服務費用只能編輯金額")

            paid_amount = _to_float(existing[1])
            customer_code, customer_name, _ = _lookup_contract_context(cur, payload.contract_code) if payload.contract_code else (None, None, None)
            category = (payload.expense_category or "額外開銷").strip() or "額外開銷"
            service_type = category[:100]
            description = payload.description.strip()
            vendor_name = payload.vendor_name.strip() if payload.vendor_name else None
            payment_status = _calculate_service_status(payload.amount, paid_amount)
            accounting_period = accounting_period_for_date(payload.service_date)

            cur.execute("""
                UPDATE service_expense
                SET contract_code = %s,
                    customer_code = %s,
                    customer_name = %s,
                    service_date = %s,
                    service_type = %s,
                    repair_company_code = NULL,
                    total_amount = %s,
                    adjusted_amount = NULL,
                    paid_amount = %s,
                    payment_status = %s,
                    expense_source = 'extra',
                    expense_category = %s,
                    expense_description = %s,
                    vendor_name = %s,
                    accounting_period = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, contract_code, customer_code, customer_name, service_date,
                          service_type, total_amount, adjusted_amount, paid_amount,
                          payment_status, expense_source, expense_category,
                          expense_description, vendor_name, accounting_period
            """, (
                payload.contract_code,
                customer_code,
                customer_name,
                payload.service_date,
                service_type,
                payload.amount,
                paid_amount,
                payment_status,
                category,
                description,
                vendor_name,
                accounting_period,
                expense_id,
            ))
            row = cur.fetchone()
            conn.commit()

            return {
                "id": row[0],
                "contract_code": row[1],
                "customer_code": row[2],
                "customer_name": row[3],
                "service_date": _serialize_date(row[4]),
                "service_type": row[5],
                "original_amount": _to_float(row[6]),
                "adjusted_amount": _to_float(row[7]) if row[7] is not None else None,
                "amount": _to_float(row[7]) if row[7] is not None else _to_float(row[6]),
                "paid_amount": _to_float(row[8]),
                "payment_status": _service_status_to_display(row[9]),
                "expense_source": row[10],
                "expense_category": row[11],
                "description": row[12],
                "vendor_name": row[13],
                "accounting_period": row[14],
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.delete("/service/extra/{expense_id}", status_code=204)
def delete_extra_expense(expense_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(expense_source, 'contract'), COALESCE(paid_amount, 0), payment_status
                FROM service_expense
                WHERE id = %s
                FOR UPDATE
            """, (expense_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="額外開銷不存在")
            if existing[0] != "extra":
                raise HTTPException(status_code=400, detail="只有額外開銷可以刪除")

            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM bank_ledger_reconciliation_lines
                    WHERE target_type = 'service_expense'
                      AND target_id = %s
                ) OR EXISTS (
                    SELECT 1
                    FROM bank_ledger
                    WHERE reconciled_service_expense_id = %s
                      AND is_reconciled = TRUE
                )
            """, (expense_id, expense_id))
            has_reconciliation = cur.fetchone()[0]
            if has_reconciliation or _to_float(existing[1]) > 0 or existing[2] != RECEIVABLE_UNPAID:
                raise HTTPException(status_code=400, detail="這筆額外開銷已有付款或對帳紀錄，請先取消對帳後再刪除")

            cur.execute("DELETE FROM service_expense WHERE id = %s", (expense_id,))
            conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
