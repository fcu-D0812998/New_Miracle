"""合約管理 API - 統一處理租賃/買斷，消除特殊情況"""
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Query
import re
from typing import List, Optional
from app.accounting_period import apply_accounting_period_filter
from app.database import get_connection, get_cursor
from app.models.contract import (
    ContractLeasing, ContractBuyout,
    ContractLeasingCreate, ContractBuyoutCreate,
    ContractResume
)
from app.services.contract_service import (
    generate_leasing_ar, generate_buyout_ar,
    generate_service_expenses_for_leasing, generate_service_expenses_for_buyout
)

router = APIRouter()

_LEASING_SELECT = """
    SELECT id, contract_code, customer_code, customer_name, start_date,
           model, quantity, monthly_rent, payment_cycle_months, overprint,
           contract_months, sales_company_code, sales_amount,
           service_company_code, service_amount,
           sales_payment_status, service_payment_status, status, needs_invoice,
           created_at, updated_at
    FROM contracts_leasing
    WHERE contract_code = %s
"""

_BUYOUT_SELECT = """
    SELECT id, contract_code, customer_code, customer_name, deal_date,
           deal_amount, sales_company_code, sales_amount,
           service_company_code, service_amount,
           sales_payment_status, service_payment_status, status, needs_invoice,
           created_at, updated_at
    FROM contracts_buyout
    WHERE contract_code = %s
"""

def _leasing_row_to_contract(row) -> ContractLeasing:
    return ContractLeasing(
        id=row[0], contract_code=row[1], customer_code=row[2], customer_name=row[3],
        start_date=row[4], model=row[5], quantity=row[6],
        monthly_rent=float(row[7]) if row[7] else None,
        payment_cycle_months=row[8], overprint=row[9], contract_months=row[10],
        sales_company_code=row[11], sales_amount=float(row[12]) if row[12] else None,
        service_company_code=row[13], service_amount=float(row[14]) if row[14] else None,
        sales_payment_status=row[15], service_payment_status=row[16],
        status=row[17], needs_invoice=bool(row[18]), created_at=row[19], updated_at=row[20]
    )


def _fetch_leasing(cur, contract_code: str, for_update: bool = False):
    sql = _LEASING_SELECT + (" FOR UPDATE" if for_update else "")
    cur.execute(sql, (contract_code,))
    return cur.fetchone()


def _buyout_row_to_contract(row) -> ContractBuyout:
    return ContractBuyout(
        id=row[0], contract_code=row[1], customer_code=row[2], customer_name=row[3],
        deal_date=row[4], deal_amount=float(row[5]) if row[5] else None,
        sales_company_code=row[6], sales_amount=float(row[7]) if row[7] else None,
        service_company_code=row[8], service_amount=float(row[9]) if row[9] else None,
        sales_payment_status=row[10], service_payment_status=row[11],
        status=row[12], needs_invoice=bool(row[13]), created_at=row[14], updated_at=row[15]
    )


def _fetch_buyout(cur, contract_code: str, for_update: bool = False):
    sql = _BUYOUT_SELECT + (" FOR UPDATE" if for_update else "")
    cur.execute(sql, (contract_code,))
    return cur.fetchone()


def _delete_service_expenses(cur, contract_code: str):
    cur.execute("""
        DELETE FROM service_expense
        WHERE contract_code = %s
          AND COALESCE(expense_source, 'contract') = 'contract'
    """, (contract_code,))


def resolve_customer(customer_input: str, conn) -> tuple[str, str]:
    """允許前端傳入客戶代碼或精準客戶名稱，統一轉回資料庫使用的客戶代碼。"""
    keyword = (customer_input or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="請輸入客戶名稱")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_code, name
            FROM customers
            WHERE LOWER(customer_code) = LOWER(%s)
               OR LOWER(name) = LOWER(%s)
            ORDER BY CASE WHEN LOWER(customer_code) = LOWER(%s) THEN 0 ELSE 1 END,
                     customer_code
            LIMIT 1
        """, (keyword, keyword, keyword))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="找不到客戶，請先建立客戶資料或從清單選擇")
        return row[0], row[1]


def _validate_leasing_receivable_fields(contract: ContractLeasingCreate):
    has_monthly_rent = contract.monthly_rent is not None
    has_contract_months = contract.contract_months is not None

    if has_contract_months and not has_monthly_rent:
        raise HTTPException(status_code=400, detail="租賃合約要生成應收帳款時，請填寫月租金")
    if has_monthly_rent and not has_contract_months:
        raise HTTPException(status_code=400, detail="租賃合約要生成應收帳款時，請填寫合約期數")


def _validate_buyout_receivable_fields(contract: ContractBuyoutCreate):
    if contract.deal_amount is None:
        raise HTTPException(status_code=400, detail="買斷合約要生成應收帳款時，請填寫成交金額")


def _leasing_end_date(start_date: date, contract_months: Optional[int]) -> date:
    if not start_date:
        raise HTTPException(status_code=400, detail="合約起始日不存在，無法續約")
    if not contract_months or contract_months <= 0:
        raise HTTPException(status_code=400, detail="合約期數需大於 0，無法續約")

    from app.utils.date_utils import add_months, subtract_days
    return subtract_days(add_months(start_date, contract_months), 1)


def _renewal_base_code(contract_code: str) -> str:
    match = re.match(r"^(.*)-R\d+$", contract_code)
    return match.group(1) if match else contract_code


def _next_renewal_contract_code(cur, contract_code: str) -> str:
    base_code = _renewal_base_code(contract_code)
    cur.execute("""
        SELECT contract_code
        FROM contracts_leasing
        WHERE contract_code = %s OR contract_code LIKE %s
        UNION
        SELECT contract_code
        FROM contracts_buyout
        WHERE contract_code = %s OR contract_code LIKE %s
    """, (base_code, f"{base_code}-R%", base_code, f"{base_code}-R%"))

    max_sequence = 0
    suffix_pattern = re.compile(rf"^{re.escape(base_code)}-R(\d+)$")
    for row in cur.fetchall():
        existing_code = row[0]
        match = suffix_pattern.match(existing_code)
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))

    return f"{base_code}-R{max_sequence + 1}"


@router.get("/leasing", response_model=List[ContractLeasing])
def get_leasing_contracts(
    search: Optional[str] = Query(None),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    """取得租賃合約列表"""
    where_parts = []
    params = []
    apply_accounting_period_filter(where_parts, params, "accounting_period", accounting_period)
    if search:
        where_parts.append("(contract_code ILIKE %s OR customer_name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""

    with get_cursor() as cur:
        cur.execute(f"""
                SELECT id, contract_code, customer_code, customer_name, start_date,
                       model, quantity, monthly_rent, payment_cycle_months, overprint,
                       contract_months, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status, status, needs_invoice,
                       created_at, updated_at
                FROM contracts_leasing
                {where_clause}
                ORDER BY contract_code
            """, tuple(params))
        rows = cur.fetchall()
    
    return [_leasing_row_to_contract(r) for r in rows]

@router.get("/buyout", response_model=List[ContractBuyout])
def get_buyout_contracts(
    search: Optional[str] = Query(None),
    accounting_period: Optional[str] = Query("current", description="帳務期間：current/prior/all"),
):
    """取得買斷合約列表"""
    where_parts = []
    params = []
    apply_accounting_period_filter(where_parts, params, "accounting_period", accounting_period)
    if search:
        where_parts.append("(contract_code ILIKE %s OR customer_name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""

    with get_cursor() as cur:
        cur.execute(f"""
                SELECT id, contract_code, customer_code, customer_name, deal_date,
                       deal_amount, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status, status, needs_invoice,
                       created_at, updated_at
                FROM contracts_buyout
                {where_clause}
                ORDER BY contract_code
            """, tuple(params))
        rows = cur.fetchall()
    
    return [_buyout_row_to_contract(r) for r in rows]


@router.get("/leasing/expiring-this-year")
def get_leasing_contracts_expiring_this_year(
    year: Optional[int] = Query(None, description="到期年度，預設今年"),
):
    """取得指定年度到期的租賃合約。"""
    target_year = year or date.today().year
    year_start = date(target_year, 1, 1)
    year_end = date(target_year, 12, 31)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, contract_code, customer_code, customer_name, start_date,
                   ((start_date + make_interval(months => contract_months))::date - 1) AS end_date,
                   model, quantity, monthly_rent, payment_cycle_months, overprint,
                   contract_months, sales_company_code, sales_amount,
                   service_company_code, service_amount,
                   sales_payment_status, service_payment_status, status, needs_invoice,
                   created_at, updated_at
            FROM contracts_leasing
            WHERE start_date IS NOT NULL
              AND contract_months IS NOT NULL
              AND contract_months > 0
              AND ((start_date + make_interval(months => contract_months))::date - 1)
                    BETWEEN %s AND %s
            ORDER BY end_date, contract_code
        """, (year_start, year_end))
        rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "contract_code": row[1],
            "customer_code": row[2],
            "customer_name": row[3],
            "start_date": row[4],
            "end_date": row[5],
            "model": row[6],
            "quantity": row[7],
            "monthly_rent": float(row[8]) if row[8] is not None else None,
            "payment_cycle_months": row[9],
            "overprint": row[10],
            "contract_months": row[11],
            "sales_company_code": row[12],
            "sales_amount": float(row[13]) if row[13] is not None else None,
            "service_company_code": row[14],
            "service_amount": float(row[15]) if row[15] is not None else None,
            "sales_payment_status": row[16],
            "service_payment_status": row[17],
            "status": row[18],
            "needs_invoice": bool(row[19]),
            "created_at": row[20],
            "updated_at": row[21],
        }
        for row in rows
    ]


@router.post("/leasing", response_model=ContractLeasing, status_code=201)
def create_leasing_contract(contract: ContractLeasingCreate):
    """新增租賃合約（自動生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _validate_leasing_receivable_fields(contract)
            customer_code, customer_name = resolve_customer(contract.customer_code, conn)
            
            monthly_rent = contract.monthly_rent
            
            cur.execute("""
                INSERT INTO contracts_leasing
                (contract_code, customer_code, customer_name, start_date, model,
                 quantity, monthly_rent, payment_cycle_months, overprint, contract_months,
                 sales_company_code, sales_amount, service_company_code, service_amount, needs_invoice)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contract.contract_code, customer_code, customer_name,
                contract.start_date, contract.model, contract.quantity,
                monthly_rent, contract.payment_cycle_months,
                contract.overprint, contract.contract_months,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract.needs_invoice
            ))
            
            if monthly_rent and contract.contract_months:
                generate_leasing_ar(
                    contract.contract_code, customer_code, customer_name,
                    contract.start_date, monthly_rent,
                    contract.payment_cycle_months, contract.contract_months, conn,
                    needs_invoice=contract.needs_invoice
                )
            
            # 生成服務費用
            generate_service_expenses_for_leasing(
                contract.contract_code, customer_code, customer_name,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                conn,
                effective_date=contract.start_date,
            )
            
            conn.commit()
            row = _fetch_leasing(cur, contract.contract_code)
            if not row:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _leasing_row_to_contract(row)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="合約編號已存在")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/leasing/{contract_code}/renew", response_model=ContractLeasing, status_code=201)
def renew_leasing_contract(contract_code: str):
    """依原租賃合約建立下一期續約合約，原合約不異動。"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            original = _fetch_leasing(cur, contract_code, for_update=True)
            if not original:
                raise HTTPException(status_code=404, detail="合約不存在")
            if original[17] != "active":
                raise HTTPException(status_code=400, detail="只有使用中的合約可以續約")

            original_start_date = original[4]
            contract_months = original[10]
            original_end_date = _leasing_end_date(original_start_date, contract_months)
            new_start_date = original_end_date + timedelta(days=1)
            new_contract_code = _next_renewal_contract_code(cur, contract_code)

            cur.execute("""
                INSERT INTO contracts_leasing
                (contract_code, customer_code, customer_name, start_date, model,
                 quantity, monthly_rent, payment_cycle_months, overprint, contract_months,
                 sales_company_code, sales_amount, service_company_code, service_amount, needs_invoice)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                new_contract_code,
                original[2],
                original[3],
                new_start_date,
                original[5],
                original[6],
                original[7],
                original[8],
                original[9],
                original[10],
                original[11],
                original[12],
                original[13],
                original[14],
                bool(original[18]),
            ))

            monthly_rent = float(original[7]) if original[7] is not None else None
            if monthly_rent and contract_months:
                generate_leasing_ar(
                    new_contract_code,
                    original[2],
                    original[3],
                    new_start_date,
                    monthly_rent,
                    original[8],
                    contract_months,
                    conn,
                    needs_invoice=bool(original[18]),
                )

            generate_service_expenses_for_leasing(
                new_contract_code,
                original[2],
                original[3],
                original[11],
                float(original[12]) if original[12] is not None else None,
                original[13],
                float(original[14]) if original[14] is not None else None,
                conn,
                effective_date=new_start_date,
            )

            conn.commit()
            row = _fetch_leasing(cur, new_contract_code)
            if not row:
                raise HTTPException(status_code=500, detail="續約合約讀取失敗")
            return _leasing_row_to_contract(row)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="續約合約編號已存在，請重試")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/buyout", response_model=ContractBuyout, status_code=201)
def create_buyout_contract(contract: ContractBuyoutCreate):
    """新增買斷合約（自動生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _validate_buyout_receivable_fields(contract)
            customer_code, customer_name = resolve_customer(contract.customer_code, conn)
            
            deal_amount = contract.deal_amount
            
            cur.execute("""
                INSERT INTO contracts_buyout
                (contract_code, customer_code, customer_name, deal_date, deal_amount,
                 sales_company_code, sales_amount, service_company_code, service_amount, needs_invoice)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contract.contract_code, customer_code, customer_name,
                contract.deal_date, deal_amount,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract.needs_invoice
            ))
            
            if deal_amount:
                generate_buyout_ar(
                    contract.contract_code, customer_code, customer_name,
                    contract.deal_date, deal_amount, conn,
                    needs_invoice=contract.needs_invoice
                )
            
            # 生成服務費用
            generate_service_expenses_for_buyout(
                contract.contract_code, customer_code, customer_name,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                conn,
                effective_date=contract.deal_date,
            )
            
            conn.commit()
            row = _fetch_buyout(cur, contract.contract_code)
            if not row:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _buyout_row_to_contract(row)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="合約編號已存在")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.put("/leasing/{contract_code}", response_model=ContractLeasing)
def update_leasing_contract(contract_code: str, contract: ContractLeasingCreate):
    """更新租賃合約（重新生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _validate_leasing_receivable_fields(contract)
            customer_code, customer_name = resolve_customer(contract.customer_code, conn)
            new_contract_code = contract.contract_code
            code_changed = new_contract_code != contract_code

            if code_changed:
                cur.execute(
                    "SELECT 1 FROM contracts_leasing WHERE contract_code = %s",
                    (new_contract_code,)
                )
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="合約編號已存在")
            
            monthly_rent = contract.monthly_rent
            
            should_generate = bool(monthly_rent and contract.contract_months)

            cur.execute("""
                UPDATE contracts_leasing
                SET contract_code = %s,
                    customer_code = %s, customer_name = %s, start_date = %s,
                    model = %s, quantity = %s, monthly_rent = %s,
                    payment_cycle_months = %s, overprint = %s, contract_months = %s,
                    sales_company_code = %s, sales_amount = %s,
                    service_company_code = %s, service_amount = %s,
                    needs_invoice = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
                RETURNING id, contract_code, sales_payment_status, service_payment_status,
                         status, created_at, updated_at
            """, (
                new_contract_code,
                customer_code, customer_name, contract.start_date,
                contract.model, contract.quantity, monthly_rent,
                contract.payment_cycle_months, contract.overprint, contract.contract_months,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract.needs_invoice,
                contract_code
            ))
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")

            if should_generate:
                cur.execute("DELETE FROM ar_leasing WHERE contract_code IN (%s, %s)", (contract_code, new_contract_code))
                generate_leasing_ar(
                    new_contract_code, customer_code, customer_name,
                    contract.start_date, monthly_rent,
                    contract.payment_cycle_months, contract.contract_months, conn,
                    needs_invoice=contract.needs_invoice
                )
            elif code_changed:
                cur.execute(
                    "UPDATE ar_leasing SET contract_code = %s WHERE contract_code = %s",
                    (new_contract_code, contract_code)
                )
            
            # 更新服務費用（處理合約編號變更）
            if code_changed:
                cur.execute(
                    "UPDATE service_expense SET contract_code = %s WHERE contract_code = %s",
                    (new_contract_code, contract_code)
                )
            
            # 生成/更新服務費用
            generate_service_expenses_for_leasing(
                new_contract_code, customer_code, customer_name,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                conn,
                effective_date=contract.start_date,
            )
            
            conn.commit()
            refreshed = _fetch_leasing(cur, new_contract_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _leasing_row_to_contract(refreshed)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.put("/buyout/{contract_code}", response_model=ContractBuyout)
def update_buyout_contract(contract_code: str, contract: ContractBuyoutCreate):
    """更新買斷合約（重新生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _validate_buyout_receivable_fields(contract)
            customer_code, customer_name = resolve_customer(contract.customer_code, conn)
            new_contract_code = contract.contract_code
            code_changed = new_contract_code != contract_code

            if code_changed:
                cur.execute(
                    "SELECT 1 FROM contracts_buyout WHERE contract_code = %s",
                    (new_contract_code,)
                )
                if cur.fetchone():
                    raise HTTPException(status_code=400, detail="合約編號已存在")
            
            deal_amount = contract.deal_amount
            
            should_generate = bool(deal_amount)

            cur.execute("""
                UPDATE contracts_buyout
                SET contract_code = %s,
                    customer_code = %s, customer_name = %s, deal_date = %s,
                    deal_amount = %s, sales_company_code = %s, sales_amount = %s,
                    service_company_code = %s, service_amount = %s,
                    needs_invoice = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
                RETURNING id, contract_code, sales_payment_status, service_payment_status,
                         status, created_at, updated_at
            """, (
                new_contract_code,
                customer_code, customer_name, contract.deal_date,
                deal_amount, contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract.needs_invoice,
                contract_code
            ))
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")

            if should_generate:
                cur.execute("DELETE FROM ar_buyout WHERE contract_code IN (%s, %s)", (contract_code, new_contract_code))
                generate_buyout_ar(
                    new_contract_code, customer_code, customer_name,
                    contract.deal_date, deal_amount, conn,
                    needs_invoice=contract.needs_invoice
                )
            elif code_changed:
                cur.execute(
                    "UPDATE ar_buyout SET contract_code = %s WHERE contract_code = %s",
                    (new_contract_code, contract_code)
                )
            
            # 更新服務費用（處理合約編號變更）
            if code_changed:
                cur.execute(
                    "UPDATE service_expense SET contract_code = %s WHERE contract_code = %s",
                    (new_contract_code, contract_code)
                )
            
            # 生成/更新服務費用
            generate_service_expenses_for_buyout(
                new_contract_code, customer_code, customer_name,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                conn,
                effective_date=contract.deal_date,
            )
            
            conn.commit()
            refreshed = _fetch_buyout(cur, new_contract_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _buyout_row_to_contract(refreshed)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/leasing/{contract_code}/pause", response_model=ContractLeasing)
def pause_leasing_contract(contract_code: str):
    """將租賃合約標記為暫停並刪除既有應收帳款"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row = _fetch_leasing(cur, contract_code, for_update=True)
            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")
            if row[17] == "paused":
                raise HTTPException(status_code=400, detail="合約已為暫停狀態")

            cur.execute("""
                UPDATE contracts_leasing
                SET status = 'paused', updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
            """, (contract_code,))
            cur.execute("DELETE FROM ar_leasing WHERE contract_code = %s", (contract_code,))
            _delete_service_expenses(cur, contract_code)

            conn.commit()
            refreshed = _fetch_leasing(cur, contract_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _leasing_row_to_contract(refreshed)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/leasing/{contract_code}/resume", response_model=ContractLeasing)
def resume_leasing_contract(contract_code: str, payload: ContractResume):
    """恢復租賃合約並重新產生應收帳款"""
    resume_date = payload.resume_date or date.today()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row = _fetch_leasing(cur, contract_code, for_update=True)
            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")
            if row[17] != "paused":
                raise HTTPException(status_code=400, detail="合約目前不是暫停狀態")

            monthly_rent = float(row[7]) if row[7] else None
            contract_months = row[10]

            cur.execute("""
                UPDATE contracts_leasing
                SET status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
            """, (contract_code,))
            cur.execute("DELETE FROM ar_leasing WHERE contract_code = %s", (contract_code,))

            if monthly_rent and contract_months:
                generate_leasing_ar(
                    contract_code,
                    row[2],
                    row[3],
                    resume_date,
                    monthly_rent,
                    row[8],
                    contract_months,
                    conn,
                    needs_invoice=bool(row[18])
                )
            generate_service_expenses_for_leasing(
                contract_code,
                row[2],
                row[3],
                row[11],
                float(row[12]) if row[12] else None,
                row[13],
                float(row[14]) if row[14] else None,
                conn,
                effective_date=resume_date,
            )

            conn.commit()
            refreshed = _fetch_leasing(cur, contract_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _leasing_row_to_contract(refreshed)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/buyout/{contract_code}/pause", response_model=ContractBuyout)
def pause_buyout_contract(contract_code: str):
    """將買斷合約標記為暫停並刪除既有應收帳款"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row = _fetch_buyout(cur, contract_code, for_update=True)
            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")
            if row[12] == "paused":
                raise HTTPException(status_code=400, detail="合約已為暫停狀態")

            cur.execute("""
                UPDATE contracts_buyout
                SET status = 'paused', updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
            """, (contract_code,))
            cur.execute("DELETE FROM ar_buyout WHERE contract_code = %s", (contract_code,))
            _delete_service_expenses(cur, contract_code)

            conn.commit()
            refreshed = _fetch_buyout(cur, contract_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _buyout_row_to_contract(refreshed)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/buyout/{contract_code}/resume", response_model=ContractBuyout)
def resume_buyout_contract(contract_code: str, payload: ContractResume):
    """恢復買斷合約並重新產生應收帳款"""
    resume_date = payload.resume_date or date.today()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row = _fetch_buyout(cur, contract_code, for_update=True)
            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")
            if row[12] != "paused":
                raise HTTPException(status_code=400, detail="合約目前不是暫停狀態")

            deal_amount = float(row[5]) if row[5] else None

            cur.execute("""
                UPDATE contracts_buyout
                SET status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
            """, (contract_code,))
            cur.execute("DELETE FROM ar_buyout WHERE contract_code = %s", (contract_code,))

            if deal_amount:
                generate_buyout_ar(
                    contract_code,
                    row[2],
                    row[3],
                    resume_date,
                    deal_amount,
                    conn,
                    needs_invoice=bool(row[13])
                )
            generate_service_expenses_for_buyout(
                contract_code,
                row[2],
                row[3],
                row[6],
                float(row[7]) if row[7] else None,
                row[8],
                float(row[9]) if row[9] else None,
                conn,
                effective_date=resume_date,
            )

            conn.commit()
            refreshed = _fetch_buyout(cur, contract_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _buyout_row_to_contract(refreshed)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/leasing/{contract_code}", status_code=204)
def delete_leasing_contract(contract_code: str):
    """刪除租賃合約（連帶刪除應收帳款和服務費用）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ar_leasing WHERE contract_code = %s", (contract_code,))
            _delete_service_expenses(cur, contract_code)
            cur.execute("DELETE FROM contracts_leasing WHERE contract_code = %s", (contract_code,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="合約不存在")
            conn.commit()
    finally:
        conn.close()

@router.delete("/buyout/{contract_code}", status_code=204)
def delete_buyout_contract(contract_code: str):
    """刪除買斷合約（連帶刪除應收帳款和服務費用）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ar_buyout WHERE contract_code = %s", (contract_code,))
            _delete_service_expenses(cur, contract_code)
            cur.execute("DELETE FROM contracts_buyout WHERE contract_code = %s", (contract_code,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="合約不存在")
            conn.commit()
    finally:
        conn.close()
