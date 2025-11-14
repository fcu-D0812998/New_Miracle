"""合約管理 API - 統一處理租賃/買斷，消除特殊情況"""
from datetime import date
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.database import get_connection, get_cursor
from app.models.contract import (
    ContractLeasing, ContractBuyout,
    ContractLeasingCreate, ContractBuyoutCreate,
    ContractResume
)
from app.services.contract_service import generate_leasing_ar, generate_buyout_ar

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


def get_customer_name(customer_code: str, conn) -> str:
    """取得客戶名稱"""
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM customers WHERE customer_code = %s", (customer_code,))
        row = cur.fetchone()
        return row[0] if row else ""

@router.get("/leasing", response_model=List[ContractLeasing])
def get_leasing_contracts(search: Optional[str] = Query(None)):
    """取得租賃合約列表"""
    with get_cursor() as cur:
        if search:
            cur.execute("""
                SELECT id, contract_code, customer_code, customer_name, start_date,
                       model, quantity, monthly_rent, payment_cycle_months, overprint,
                       contract_months, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status, status, needs_invoice,
                       created_at, updated_at
                FROM contracts_leasing
                WHERE contract_code ILIKE %s OR customer_name ILIKE %s
                ORDER BY contract_code
            """, (f"%{search}%", f"%{search}%"))
        else:
            cur.execute("""
                SELECT id, contract_code, customer_code, customer_name, start_date,
                       model, quantity, monthly_rent, payment_cycle_months, overprint,
                       contract_months, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status, status, needs_invoice,
                       created_at, updated_at
                FROM contracts_leasing
                ORDER BY contract_code
            """)
        rows = cur.fetchall()
    
    return [_leasing_row_to_contract(r) for r in rows]

@router.get("/buyout", response_model=List[ContractBuyout])
def get_buyout_contracts(search: Optional[str] = Query(None)):
    """取得買斷合約列表"""
    with get_cursor() as cur:
        if search:
            cur.execute("""
                SELECT id, contract_code, customer_code, customer_name, deal_date,
                       deal_amount, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status, status, needs_invoice,
                       created_at, updated_at
                FROM contracts_buyout
                WHERE contract_code ILIKE %s OR customer_name ILIKE %s
                ORDER BY contract_code
            """, (f"%{search}%", f"%{search}%"))
        else:
            cur.execute("""
                SELECT id, contract_code, customer_code, customer_name, deal_date,
                       deal_amount, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status, status, needs_invoice,
                       created_at, updated_at
                FROM contracts_buyout
                ORDER BY contract_code
            """)
        rows = cur.fetchall()
    
    return [_buyout_row_to_contract(r) for r in rows]

@router.post("/leasing", response_model=ContractLeasing, status_code=201)
def create_leasing_contract(contract: ContractLeasingCreate):
    """新增租賃合約（自動生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            customer_name = get_customer_name(contract.customer_code, conn)
            
            monthly_rent = contract.monthly_rent
            if contract.needs_invoice and monthly_rent:
                monthly_rent = monthly_rent * 1.05
            
            cur.execute("""
                INSERT INTO contracts_leasing
                (contract_code, customer_code, customer_name, start_date, model,
                 quantity, monthly_rent, payment_cycle_months, overprint, contract_months,
                 sales_company_code, sales_amount, service_company_code, service_amount, needs_invoice)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contract.contract_code, contract.customer_code, customer_name,
                contract.start_date, contract.model, contract.quantity,
                monthly_rent, contract.payment_cycle_months,
                contract.overprint, contract.contract_months,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract.needs_invoice
            ))
            
            if monthly_rent and contract.contract_months:
                generate_leasing_ar(
                    contract.contract_code, contract.customer_code, customer_name,
                    contract.start_date, monthly_rent,
                    contract.payment_cycle_months, contract.contract_months, conn
                )
            
            conn.commit()
            row = _fetch_leasing(cur, contract.contract_code)
            if not row:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _leasing_row_to_contract(row)
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="合約編號已存在")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/buyout", response_model=ContractBuyout, status_code=201)
def create_buyout_contract(contract: ContractBuyoutCreate):
    """新增買斷合約（自動生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            customer_name = get_customer_name(contract.customer_code, conn)
            
            deal_amount = contract.deal_amount
            if contract.needs_invoice and deal_amount:
                deal_amount = deal_amount * 1.05
            
            cur.execute("""
                INSERT INTO contracts_buyout
                (contract_code, customer_code, customer_name, deal_date, deal_amount,
                 sales_company_code, sales_amount, service_company_code, service_amount, needs_invoice)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contract.contract_code, contract.customer_code, customer_name,
                contract.deal_date, deal_amount,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract.needs_invoice
            ))
            
            if deal_amount:
                generate_buyout_ar(
                    contract.contract_code, contract.customer_code, customer_name,
                    contract.deal_date, deal_amount, conn
                )
            
            conn.commit()
            row = _fetch_buyout(cur, contract.contract_code)
            if not row:
                raise HTTPException(status_code=500, detail="合約讀取失敗")
            return _buyout_row_to_contract(row)
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
            customer_name = get_customer_name(contract.customer_code, conn)
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
            if contract.needs_invoice and monthly_rent:
                monthly_rent = monthly_rent * 1.05
            
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
                contract.customer_code, customer_name, contract.start_date,
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
                    new_contract_code, contract.customer_code, customer_name,
                    contract.start_date, monthly_rent,
                    contract.payment_cycle_months, contract.contract_months, conn
                )
            elif code_changed:
                cur.execute(
                    "UPDATE ar_leasing SET contract_code = %s WHERE contract_code = %s",
                    (new_contract_code, contract_code)
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
            customer_name = get_customer_name(contract.customer_code, conn)
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
            if contract.needs_invoice and deal_amount:
                deal_amount = deal_amount * 1.05
            
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
                contract.customer_code, customer_name, contract.deal_date,
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
                    new_contract_code, contract.customer_code, customer_name,
                    contract.deal_date, deal_amount, conn
                )
            elif code_changed:
                cur.execute(
                    "UPDATE ar_buyout SET contract_code = %s WHERE contract_code = %s",
                    (new_contract_code, contract_code)
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
                    conn
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
                    conn
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
    """刪除租賃合約（連帶刪除應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ar_leasing WHERE contract_code = %s", (contract_code,))
            cur.execute("DELETE FROM contracts_leasing WHERE contract_code = %s", (contract_code,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="合約不存在")
            conn.commit()
    finally:
        conn.close()

@router.delete("/buyout/{contract_code}", status_code=204)
def delete_buyout_contract(contract_code: str):
    """刪除買斷合約（連帶刪除應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ar_buyout WHERE contract_code = %s", (contract_code,))
            cur.execute("DELETE FROM contracts_buyout WHERE contract_code = %s", (contract_code,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="合約不存在")
            conn.commit()
    finally:
        conn.close()

