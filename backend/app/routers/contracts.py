"""合約管理 API - 統一處理租賃/買斷，消除特殊情況"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.database import get_connection, get_cursor
from app.models.contract import (
    ContractLeasing, ContractBuyout,
    ContractLeasingCreate, ContractBuyoutCreate
)
from app.services.contract_service import generate_leasing_ar, generate_buyout_ar

router = APIRouter()

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
                       sales_payment_status, service_payment_status,
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
                       sales_payment_status, service_payment_status,
                       created_at, updated_at
                FROM contracts_leasing
                ORDER BY contract_code
            """)
        rows = cur.fetchall()
    
    return [
        ContractLeasing(
            id=r[0], contract_code=r[1], customer_code=r[2], customer_name=r[3],
            start_date=r[4], model=r[5], quantity=r[6], monthly_rent=float(r[7]) if r[7] else None,
            payment_cycle_months=r[8], overprint=r[9], contract_months=r[10],
            sales_company_code=r[11], sales_amount=float(r[12]) if r[12] else None,
            service_company_code=r[13], service_amount=float(r[14]) if r[14] else None,
            sales_payment_status=r[15], service_payment_status=r[16],
            created_at=r[17], updated_at=r[18]
        ) for r in rows
    ]

@router.get("/buyout", response_model=List[ContractBuyout])
def get_buyout_contracts(search: Optional[str] = Query(None)):
    """取得買斷合約列表"""
    with get_cursor() as cur:
        if search:
            cur.execute("""
                SELECT id, contract_code, customer_code, customer_name, deal_date,
                       deal_amount, sales_company_code, sales_amount,
                       service_company_code, service_amount,
                       sales_payment_status, service_payment_status,
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
                       sales_payment_status, service_payment_status,
                       created_at, updated_at
                FROM contracts_buyout
                ORDER BY contract_code
            """)
        rows = cur.fetchall()
    
    return [
        ContractBuyout(
            id=r[0], contract_code=r[1], customer_code=r[2], customer_name=r[3],
            deal_date=r[4], deal_amount=float(r[5]) if r[5] else None,
            sales_company_code=r[6], sales_amount=float(r[7]) if r[7] else None,
            service_company_code=r[8], service_amount=float(r[9]) if r[9] else None,
            sales_payment_status=r[10], service_payment_status=r[11],
            created_at=r[12], updated_at=r[13]
        ) for r in rows
    ]

@router.post("/leasing", response_model=ContractLeasing, status_code=201)
def create_leasing_contract(contract: ContractLeasingCreate):
    """新增租賃合約（自動生成應收帳款）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            customer_name = get_customer_name(contract.customer_code, conn)
            
            cur.execute("""
                INSERT INTO contracts_leasing
                (contract_code, customer_code, customer_name, start_date, model,
                 quantity, monthly_rent, payment_cycle_months, overprint, contract_months,
                 sales_company_code, sales_amount, service_company_code, service_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, sales_payment_status, service_payment_status,
                         created_at, updated_at
            """, (
                contract.contract_code, contract.customer_code, customer_name,
                contract.start_date, contract.model, contract.quantity,
                contract.monthly_rent, contract.payment_cycle_months,
                contract.overprint, contract.contract_months,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount
            ))
            row = cur.fetchone()
            
            if contract.monthly_rent and contract.contract_months:
                generate_leasing_ar(
                    contract.contract_code, contract.customer_code, customer_name,
                    contract.start_date, contract.monthly_rent,
                    contract.payment_cycle_months, contract.contract_months, conn
                )
            
            conn.commit()
            return ContractLeasing(
                id=row[0], contract_code=contract.contract_code,
                customer_code=contract.customer_code, customer_name=customer_name,
                start_date=contract.start_date, model=contract.model,
                quantity=contract.quantity, monthly_rent=contract.monthly_rent,
                payment_cycle_months=contract.payment_cycle_months,
                overprint=contract.overprint, contract_months=contract.contract_months,
                sales_company_code=contract.sales_company_code,
                sales_amount=contract.sales_amount,
                service_company_code=contract.service_company_code,
                service_amount=contract.service_amount,
                sales_payment_status=row[1], service_payment_status=row[2],
                created_at=row[3], updated_at=row[4]
            )
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
            
            cur.execute("""
                INSERT INTO contracts_buyout
                (contract_code, customer_code, customer_name, deal_date, deal_amount,
                 sales_company_code, sales_amount, service_company_code, service_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, sales_payment_status, service_payment_status,
                         created_at, updated_at
            """, (
                contract.contract_code, contract.customer_code, customer_name,
                contract.deal_date, contract.deal_amount,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount
            ))
            row = cur.fetchone()
            
            if contract.deal_amount:
                generate_buyout_ar(
                    contract.contract_code, contract.customer_code, customer_name,
                    contract.deal_date, contract.deal_amount, conn
                )
            
            conn.commit()
            return ContractBuyout(
                id=row[0], contract_code=contract.contract_code,
                customer_code=contract.customer_code, customer_name=customer_name,
                deal_date=contract.deal_date, deal_amount=contract.deal_amount,
                sales_company_code=contract.sales_company_code,
                sales_amount=contract.sales_amount,
                service_company_code=contract.service_company_code,
                service_amount=contract.service_amount,
                sales_payment_status=row[1], service_payment_status=row[2],
                created_at=row[3], updated_at=row[4]
            )
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
            
            cur.execute("""
                UPDATE contracts_leasing
                SET customer_code = %s, customer_name = %s, start_date = %s,
                    model = %s, quantity = %s, monthly_rent = %s,
                    payment_cycle_months = %s, overprint = %s, contract_months = %s,
                    sales_company_code = %s, sales_amount = %s,
                    service_company_code = %s, service_amount = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
                RETURNING id, sales_payment_status, service_payment_status,
                         created_at, updated_at
            """, (
                contract.customer_code, customer_name, contract.start_date,
                contract.model, contract.quantity, contract.monthly_rent,
                contract.payment_cycle_months, contract.overprint, contract.contract_months,
                contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract_code
            ))
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")
            
            if contract.monthly_rent and contract.contract_months:
                generate_leasing_ar(
                    contract_code, contract.customer_code, customer_name,
                    contract.start_date, contract.monthly_rent,
                    contract.payment_cycle_months, contract.contract_months, conn
                )
            
            conn.commit()
            return ContractLeasing(
                id=row[0], contract_code=contract_code,
                customer_code=contract.customer_code, customer_name=customer_name,
                start_date=contract.start_date, model=contract.model,
                quantity=contract.quantity, monthly_rent=contract.monthly_rent,
                payment_cycle_months=contract.payment_cycle_months,
                overprint=contract.overprint, contract_months=contract.contract_months,
                sales_company_code=contract.sales_company_code,
                sales_amount=contract.sales_amount,
                service_company_code=contract.service_company_code,
                service_amount=contract.service_amount,
                sales_payment_status=row[1], service_payment_status=row[2],
                created_at=row[3], updated_at=row[4]
            )
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
            
            cur.execute("""
                UPDATE contracts_buyout
                SET customer_code = %s, customer_name = %s, deal_date = %s,
                    deal_amount = %s, sales_company_code = %s, sales_amount = %s,
                    service_company_code = %s, service_amount = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE contract_code = %s
                RETURNING id, sales_payment_status, service_payment_status,
                         created_at, updated_at
            """, (
                contract.customer_code, customer_name, contract.deal_date,
                contract.deal_amount, contract.sales_company_code, contract.sales_amount,
                contract.service_company_code, contract.service_amount,
                contract_code
            ))
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="合約不存在")
            
            if contract.deal_amount:
                generate_buyout_ar(
                    contract_code, contract.customer_code, customer_name,
                    contract.deal_date, contract.deal_amount, conn
                )
            
            conn.commit()
            return ContractBuyout(
                id=row[0], contract_code=contract_code,
                customer_code=contract.customer_code, customer_name=customer_name,
                deal_date=contract.deal_date, deal_amount=contract.deal_amount,
                sales_company_code=contract.sales_company_code,
                sales_amount=contract.sales_amount,
                service_company_code=contract.service_company_code,
                service_amount=contract.service_amount,
                sales_payment_status=row[1], service_payment_status=row[2],
                created_at=row[3], updated_at=row[4]
            )
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

