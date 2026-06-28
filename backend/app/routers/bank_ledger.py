"""銀行帳本與對帳 API。"""
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
