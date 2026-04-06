"""銀行帳本 API"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import date
from app.database import get_cursor, get_connection
from pydantic import BaseModel

router = APIRouter()

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

class ReconcileRequest(BaseModel):
    reconcile_type: str  # "receivable" 或 "service_expense"
    ar_id: Optional[int] = None  # 應收帳款 ID（收入對帳時）
    ar_type: Optional[str] = None  # 應收帳款類型（租賃/買斷）
    service_expense_id: Optional[int] = None  # 服務費用 ID（支出對帳時）
    fee_amount: float = 0  # 對帳時額外輸入的手續費（累加到應收帳款）
    auto_update: bool = True  # 是否自動更新應收/應付帳款

class BankLedgerCreate(BankLedgerBase):
    pass

class BankLedgerUpdate(BankLedgerBase):
    pass

class BankLedger(BankLedgerBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _normalize_ar_type(ar_type: Optional[str]) -> Optional[str]:
    if not ar_type:
        return None
    value = str(ar_type).strip().lower()
    if value in {"租賃", "租赁", "leasing", "lease"}:
        return "租賃"
    if value in {"買斷", "买断", "buyout"}:
        return "買斷"
    return None

def _row_to_ledger(row) -> dict:
    """將資料庫查詢結果轉換為字典"""
    return {
        'id': row[0],
        'txn_date': row[1].strftime('%Y-%m-%d') if row[1] else None,
        'payer': row[2],
        'expense': float(row[3]) if row[3] else 0,
        'income': float(row[4]) if row[4] else 0,
        'note': row[5],
        'is_reconciled': bool(row[6]) if row[6] is not None else False,
        'reconciled_ar_id': row[7],
        'reconciled_ar_type': row[8],
        'reconciled_payable_contract_code': row[9],
        'reconciled_payable_type': row[10],
        'reconciled_service_expense_id': row[11],
        'reconciled_fee_amount': float(row[12]) if row[12] else 0,
        'created_at': row[13].strftime('%Y-%m-%d %H:%M:%S') if row[13] else None,
        'updated_at': row[14].strftime('%Y-%m-%d %H:%M:%S') if row[14] else None
    }

@router.get("", response_model=List[dict])
def get_bank_ledger(
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="搜尋關鍵字")
):
    """取得銀行帳本列表（支援日期範圍和搜尋）"""
    with get_cursor() as cur:
        where_parts = []
        params = []
        
        if from_date:
            where_parts.append("txn_date >= %s")
            params.append(from_date)
        
        if to_date:
            where_parts.append("txn_date <= %s")
            params.append(to_date)
        
        if search:
            where_parts.append("(payer ILIKE %s OR note ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        cur.execute(f"""
            SELECT id, txn_date, payer, expense, income, note,
                   is_reconciled, reconciled_ar_id, reconciled_ar_type,
                   reconciled_payable_contract_code, reconciled_payable_type,
                   reconciled_service_expense_id, reconciled_fee_amount,
                   created_at, updated_at
            FROM bank_ledger
            {where_clause}
            ORDER BY txn_date DESC, id DESC
        """, tuple(params))
        
        rows = cur.fetchall()
        return [_row_to_ledger(row) for row in rows]

@router.post("", response_model=dict, status_code=201)
def create_bank_ledger(ledger: BankLedgerCreate):
    """新增銀行帳本記錄"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bank_ledger
                (txn_date, payer, expense, income, note, is_reconciled,
                 reconciled_ar_id, reconciled_ar_type,
                 reconciled_payable_contract_code, reconciled_payable_type,
                 reconciled_service_expense_id, reconciled_fee_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, txn_date, payer, expense, income, note,
                         is_reconciled, reconciled_ar_id, reconciled_ar_type,
                         reconciled_payable_contract_code, reconciled_payable_type,
                         reconciled_service_expense_id, reconciled_fee_amount,
                         created_at, updated_at
            """, (
                ledger.txn_date, ledger.payer, ledger.expense, ledger.income,
                ledger.note, ledger.is_reconciled,
                ledger.reconciled_ar_id, ledger.reconciled_ar_type,
                ledger.reconciled_payable_contract_code, ledger.reconciled_payable_type,
                ledger.reconciled_service_expense_id, ledger.reconciled_fee_amount
            ))
            
            row = cur.fetchone()
            conn.commit()
            
            if not row:
                raise HTTPException(status_code=500, detail="記錄建立失敗")
            
            return _row_to_ledger(row)
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.put("/{id}", response_model=dict)
def update_bank_ledger(id: int, ledger: BankLedgerUpdate):
    """更新銀行帳本記錄"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bank_ledger
                SET txn_date = %s, payer = %s, expense = %s, income = %s,
                    note = %s, is_reconciled = %s,
                    reconciled_ar_id = %s, reconciled_ar_type = %s,
                    reconciled_payable_contract_code = %s, reconciled_payable_type = %s,
                    reconciled_service_expense_id = %s,
                    reconciled_fee_amount = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, txn_date, payer, expense, income, note,
                         is_reconciled, reconciled_ar_id, reconciled_ar_type,
                         reconciled_payable_contract_code, reconciled_payable_type,
                         reconciled_service_expense_id, reconciled_fee_amount,
                         created_at, updated_at
            """, (
                ledger.txn_date, ledger.payer, ledger.expense, ledger.income,
                ledger.note, ledger.is_reconciled,
                ledger.reconciled_ar_id, ledger.reconciled_ar_type,
                ledger.reconciled_payable_contract_code, ledger.reconciled_payable_type,
                ledger.reconciled_service_expense_id, ledger.reconciled_fee_amount,
                id
            ))
            
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="記錄不存在")
            
            conn.commit()
            return _row_to_ledger(row)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/{id}", status_code=204)
def delete_bank_ledger(id: int):
    """刪除銀行帳本記錄"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bank_ledger WHERE id = %s", (id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="記錄不存在")
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/reconcilable/receivables")
def get_reconcilable_receivables(
    search: Optional[str] = Query(None, description="搜尋關鍵字（合約編號、客戶名稱）"),
    type: Optional[str] = Query(None, description="類型（租賃/買斷）")
):
    """取得可對帳的應收帳款（只顯示未收和部分收款）"""
    with get_cursor() as cur:
        where_parts = ["payment_status IN ('未收', '部分收款')"]
        params = []
        
        if search:
            where_parts.append("(contract_code ILIKE %s OR customer_name ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        if type:
            # 根據類型決定查詢哪個表
            if type == '租賃':
                cur.execute(f"""
                    SELECT 
                        id, '租賃' as type, contract_code, customer_code, customer_name,
                        start_date as date, end_date,
                        total_rent as amount, fee, received_amount, payment_status,
                        (total_rent + COALESCE(fee, 0) - COALESCE(received_amount, 0)) as unpaid_amount
                    FROM ar_leasing
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY contract_code
                """, tuple(params))
                rows = cur.fetchall()
            elif type == '買斷':
                cur.execute(f"""
                    SELECT 
                        id, '買斷' as type, contract_code, customer_code, customer_name,
                        deal_date as date, NULL as end_date,
                        total_amount as amount, fee, received_amount, payment_status,
                        (total_amount + COALESCE(fee, 0) - COALESCE(received_amount, 0)) as unpaid_amount
                    FROM ar_buyout
                    WHERE {' AND '.join(where_parts)}
                    ORDER BY contract_code
                """, tuple(params))
                rows = cur.fetchall()
            else:
                rows = []
        else:
            # 查詢所有類型
            leasing_rows = []
            buyout_rows = []
            
            cur.execute(f"""
                SELECT 
                    id, '租賃' as type, contract_code, customer_code, customer_name,
                    start_date as date, end_date,
                    total_rent as amount, fee, received_amount, payment_status,
                    (total_rent + COALESCE(fee, 0) - COALESCE(received_amount, 0)) as unpaid_amount
                FROM ar_leasing
                WHERE {' AND '.join(where_parts)}
                ORDER BY contract_code
            """, tuple(params))
            leasing_rows = cur.fetchall()
            
            cur.execute(f"""
                SELECT 
                    id, '買斷' as type, contract_code, customer_code, customer_name,
                    deal_date as date, NULL as end_date,
                    total_amount as amount, fee, received_amount, payment_status,
                    (total_amount + COALESCE(fee, 0) - COALESCE(received_amount, 0)) as unpaid_amount
                FROM ar_buyout
                WHERE {' AND '.join(where_parts)}
                ORDER BY contract_code
            """, tuple(params))
            buyout_rows = cur.fetchall()
            
            rows = leasing_rows + buyout_rows
        
        # 轉換為字典
        columns = ['id', 'type', 'contract_code', 'customer_code', 'customer_name',
                   'date', 'end_date', 'amount', 'fee', 'received_amount', 'payment_status', 'unpaid_amount']
        
        result = []
        for row in rows:
            item = dict(zip(columns, row))
            # 轉換日期
            if item['date']:
                item['date'] = item['date'].strftime('%Y-%m-%d') if hasattr(item['date'], 'strftime') else str(item['date'])
            if item['end_date']:
                item['end_date'] = item['end_date'].strftime('%Y-%m-%d') if hasattr(item['end_date'], 'strftime') else str(item['end_date'])
            # 確保數值為 float
            item['amount'] = float(item['amount']) if item['amount'] else 0.0
            item['fee'] = float(item['fee']) if item['fee'] else 0.0
            item['received_amount'] = float(item['received_amount']) if item['received_amount'] else 0.0
            item['unpaid_amount'] = float(item['unpaid_amount']) if item['unpaid_amount'] else 0.0
            result.append(item)
        
        return result

@router.get("/reconcilable/service-expenses")
def get_reconcilable_service_expenses(
    search: Optional[str] = Query(None, description="搜尋關鍵字（合約編號、客戶名稱）"),
    service_type: Optional[str] = Query(None, description="服務類型（業務/維護）")
):
    """取得可對帳的服務費用（只顯示未收和部分收款）"""
    with get_cursor() as cur:
        where_parts = ["payment_status IN ('未收', '部分收款')"]
        params = []
        
        if search:
            where_parts.append("(contract_code ILIKE %s OR customer_name ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        if service_type:
            where_parts.append("service_type = %s")
            params.append(service_type)
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        cur.execute(f"""
            SELECT 
                id, contract_code, customer_code, customer_name,
                service_type, repair_company_code, total_amount, payment_status
            FROM service_expense
            {where_clause}
            ORDER BY contract_code, service_type
        """, tuple(params))
        
        rows = cur.fetchall()
        
        # 轉換為字典
        columns = ['id', 'contract_code', 'customer_code', 'customer_name',
                   'service_type', 'repair_company_code', 'total_amount', 'payment_status']
        
        result = []
        for row in rows:
            item = dict(zip(columns, row))
            item['total_amount'] = float(item['total_amount']) if item['total_amount'] else 0.0
            result.append(item)
        
        return result

@router.post("/{id}/reconcile", response_model=dict)
def reconcile_bank_ledger(id: int, request: ReconcileRequest):
    """執行對帳"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 先取得銀行帳本記錄
            cur.execute("""
                SELECT id, income, expense, is_reconciled
                FROM bank_ledger
                WHERE id = %s
            """, (id,))
            ledger_row = cur.fetchone()
            
            if not ledger_row:
                raise HTTPException(status_code=404, detail="銀行帳本記錄不存在")
            
            ledger_id, income, expense, is_reconciled = ledger_row
            
            # 轉換為 float（PostgreSQL 的 NUMERIC 類型會返回 decimal.Decimal）
            income = float(income) if income else 0.0
            expense = float(expense) if expense else 0.0
            
            if is_reconciled:
                raise HTTPException(status_code=400, detail="此記錄已對帳，請先取消對帳")
            
            # 收入對帳
            if request.reconcile_type == "receivable" and request.ar_id:
                if not income or income <= 0:
                    raise HTTPException(status_code=400, detail="此記錄不是收入記錄")
                normalized_ar_type = _normalize_ar_type(request.ar_type)
                
                # 取得應收帳款資訊
                if normalized_ar_type == "租賃":
                    cur.execute("""
                        SELECT id, total_rent, fee, received_amount, payment_status
                        FROM ar_leasing
                        WHERE id = %s
                    """, (request.ar_id,))
                elif normalized_ar_type == "買斷":
                    cur.execute("""
                        SELECT id, total_amount, fee, received_amount, payment_status
                        FROM ar_buyout
                        WHERE id = %s
                    """, (request.ar_id,))
                else:
                    raise HTTPException(status_code=400, detail="應收帳款類型錯誤")
                
                ar_row = cur.fetchone()
                if not ar_row:
                    raise HTTPException(status_code=404, detail="應收帳款不存在")
                
                ar_id, amount, fee, received_amount, payment_status = ar_row
                amount = float(amount) if amount else 0.0
                fee = float(fee) if fee else 0.0
                received_amount = float(received_amount) if received_amount else 0.0
                fee_amount = float(request.fee_amount) if request.fee_amount else 0.0
                if fee_amount < 0:
                    raise HTTPException(status_code=400, detail="手續費不可為負數")
                new_fee = fee + fee_amount
                total_amount = amount + new_fee
                
                # 更新銀行帳本
                cur.execute("""
                    UPDATE bank_ledger
                    SET is_reconciled = true,
                        reconciled_ar_id = %s,
                        reconciled_ar_type = %s,
                        reconciled_fee_amount = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (request.ar_id, normalized_ar_type, fee_amount, id))
                
                # 自動更新應收帳款
                if request.auto_update:
                    new_received_amount = received_amount + income
                    # 計算新的 payment_status
                    if new_received_amount >= total_amount:
                        new_payment_status = "已收款"
                    elif new_received_amount > 0:
                        new_payment_status = "部分收款"
                    else:
                        new_payment_status = "未收"
                    
                    if normalized_ar_type == "租賃":
                        cur.execute("""
                            UPDATE ar_leasing
                            SET fee = %s,
                                received_amount = %s,
                                payment_status = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (new_fee, new_received_amount, new_payment_status, request.ar_id))
                    else:
                        cur.execute("""
                            UPDATE ar_buyout
                            SET fee = %s,
                                received_amount = %s,
                                payment_status = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (new_fee, new_received_amount, new_payment_status, request.ar_id))
            
            # 支出對帳
            elif request.reconcile_type == "service_expense" and request.service_expense_id:
                if not expense or expense <= 0:
                    raise HTTPException(status_code=400, detail="此記錄不是支出記錄")
                
                # 取得服務費用資訊
                cur.execute("""
                    SELECT id, total_amount, payment_status
                    FROM service_expense
                    WHERE id = %s
                """, (request.service_expense_id,))
                
                se_row = cur.fetchone()
                if not se_row:
                    raise HTTPException(status_code=404, detail="服務費用不存在")
                
                se_id, total_amount, payment_status = se_row
                total_amount = float(total_amount) if total_amount else 0.0
                
                # 更新銀行帳本
                cur.execute("""
                    UPDATE bank_ledger
                    SET is_reconciled = true,
                        reconciled_service_expense_id = %s,
                        reconciled_fee_amount = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (request.service_expense_id, id))
                
                # 自動更新服務費用
                if request.auto_update:
                    cur.execute("""
                        UPDATE service_expense
                        SET payment_status = '已收款',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (request.service_expense_id,))
            else:
                raise HTTPException(status_code=400, detail="對帳類型或ID錯誤")
            
            conn.commit()
            
            # 回傳更新後的銀行帳本記錄
            cur.execute("""
                SELECT id, txn_date, payer, expense, income, note,
                       is_reconciled, reconciled_ar_id, reconciled_ar_type,
                       reconciled_payable_contract_code, reconciled_payable_type,
                       reconciled_service_expense_id, reconciled_fee_amount,
                       created_at, updated_at
                FROM bank_ledger
                WHERE id = %s
            """, (id,))
            row = cur.fetchone()
            return _row_to_ledger(row)
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/{id}/unreconcile", response_model=dict)
def unreconcile_bank_ledger(id: int, revert: bool = Query(True, description="是否還原應收/應付帳款")):
    """取消對帳"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 取得銀行帳本記錄
            cur.execute("""
                SELECT id, income, expense, is_reconciled,
                       reconciled_ar_id, reconciled_ar_type,
                       reconciled_service_expense_id, reconciled_fee_amount
                FROM bank_ledger
                WHERE id = %s
            """, (id,))
            ledger_row = cur.fetchone()
            
            if not ledger_row:
                raise HTTPException(status_code=404, detail="銀行帳本記錄不存在")
            
            ledger_id, income, expense, is_reconciled, ar_id, ar_type, se_id, reconciled_fee_amount = ledger_row
            
            # 轉換為 float（PostgreSQL 的 NUMERIC 類型會返回 decimal.Decimal）
            income = float(income) if income else 0.0
            expense = float(expense) if expense else 0.0
            reconciled_fee_amount = float(reconciled_fee_amount) if reconciled_fee_amount else 0.0
            
            if not is_reconciled:
                raise HTTPException(status_code=400, detail="此記錄未對帳")
            
            # 取消收入對帳
            normalized_ar_type = _normalize_ar_type(ar_type)
            if ar_id and normalized_ar_type:
                # 還原應收帳款
                if revert:
                    if normalized_ar_type == "租賃":
                        cur.execute("""
                            SELECT total_rent, fee, received_amount
                            FROM ar_leasing
                            WHERE id = %s
                        """, (ar_id,))
                    else:
                        cur.execute("""
                            SELECT total_amount, fee, received_amount
                            FROM ar_buyout
                            WHERE id = %s
                        """, (ar_id,))
                    
                    ar_row = cur.fetchone()
                    if ar_row:
                        amount, fee, received_amount = ar_row
                        amount = float(amount) if amount else 0.0
                        fee = float(fee) if fee else 0.0
                        received_amount = float(received_amount) if received_amount else 0.0
                        new_fee = max(0, fee - reconciled_fee_amount)
                        total_amount = amount + new_fee
                        
                        # 扣除對帳金額
                        new_received_amount = max(0, received_amount - income)
                        
                        # 計算新的 payment_status
                        if new_received_amount >= total_amount:
                            new_payment_status = "已收款"
                        elif new_received_amount > 0:
                            new_payment_status = "部分收款"
                        else:
                            new_payment_status = "未收"
                        
                        if normalized_ar_type == "租賃":
                            cur.execute("""
                                UPDATE ar_leasing
                                SET fee = %s,
                                    received_amount = %s,
                                    payment_status = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (new_fee, new_received_amount, new_payment_status, ar_id))
                        else:
                            cur.execute("""
                                UPDATE ar_buyout
                                SET fee = %s,
                                    received_amount = %s,
                                    payment_status = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (new_fee, new_received_amount, new_payment_status, ar_id))
                
                # 清除銀行帳本對帳資訊
                cur.execute("""
                    UPDATE bank_ledger
                    SET is_reconciled = false,
                        reconciled_ar_id = NULL,
                        reconciled_ar_type = NULL,
                        reconciled_fee_amount = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (id,))
            
            # 取消支出對帳
            elif se_id:
                # 還原服務費用
                if revert:
                    cur.execute("""
                        UPDATE service_expense
                        SET payment_status = '未收',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (se_id,))
                
                # 清除銀行帳本對帳資訊
                cur.execute("""
                    UPDATE bank_ledger
                    SET is_reconciled = false,
                        reconciled_service_expense_id = NULL,
                        reconciled_fee_amount = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (id,))
            else:
                raise HTTPException(status_code=400, detail="此記錄沒有對帳資訊")
            
            conn.commit()
            
            # 回傳更新後的銀行帳本記錄
            cur.execute("""
                SELECT id, txn_date, payer, expense, income, note,
                       is_reconciled, reconciled_ar_id, reconciled_ar_type,
                       reconciled_payable_contract_code, reconciled_payable_type,
                       reconciled_service_expense_id, reconciled_fee_amount,
                       created_at, updated_at
                FROM bank_ledger
                WHERE id = %s
            """, (id,))
            row = cur.fetchone()
            return _row_to_ledger(row)
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
