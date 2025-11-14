"""帳款查詢 API - 實作完整查詢邏輯"""
from fastapi import APIRouter, Query
from typing import List, Optional
from datetime import date
from app.database import get_cursor

router = APIRouter()

def row_to_dict(row, columns):
    """將資料庫查詢結果轉換為字典"""
    return dict(zip(columns, row))

@router.get("/receivables")
def get_receivables(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="繳費狀況"),
    type: Optional[str] = Query(None, description="類型（租賃/買斷）")
):
    """取得總應收帳款（合併租賃和買斷），支援多欄位查詢"""
    filters = {
        'contract_code': contract_code,
        'customer_code': customer_code,
        'customer_name': customer_name,
        'from_date': from_date,
        'to_date': to_date,
        'payment_status': payment_status
    }
    
    with get_cursor() as cur:
        # 查詢租賃應收帳款
        if not type or type == '租賃':
            where_parts = []
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
                where_parts.append("start_date >= %s")
                params.append(from_date)
            
            if to_date:
                where_parts.append("start_date <= %s")
                params.append(to_date)
            
            if payment_status:
                where_parts.append("payment_status = %s")
                params.append(payment_status)
            
            where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
            
            cur.execute(f"""
                SELECT 
                    id,
                    '租賃' as type,
                    contract_code,
                    customer_code,
                    customer_name,
                    start_date as date,
                    end_date,
                    total_rent as amount,
                    fee,
                    received_amount,
                    payment_status
                FROM ar_leasing
                {where_clause}
                ORDER BY contract_code
            """, tuple(params))
            leasing_data = cur.fetchall()
        else:
            leasing_data = []
        
        # 查詢買斷應收帳款
        if not type or type == '買斷':
            where_parts = []
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
                where_parts.append("deal_date >= %s")
                params.append(from_date)
            
            if to_date:
                where_parts.append("deal_date <= %s")
                params.append(to_date)
            
            if payment_status:
                where_parts.append("payment_status = %s")
                params.append(payment_status)
            
            where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
            
            cur.execute(f"""
                SELECT 
                    id,
                    '買斷' as type,
                    contract_code,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    NULL as end_date,
                    total_amount as amount,
                    fee,
                    received_amount,
                    payment_status
                FROM ar_buyout
                {where_clause}
                ORDER BY contract_code
            """, tuple(params))
            buyout_data = cur.fetchall()
        else:
            buyout_data = []
    
    # 合併資料並轉換為字典
    columns = ['id', 'type', 'contract_code', 'customer_code', 'customer_name', 
               'date', 'end_date', 'amount', 'fee', 'received_amount', 'payment_status']
    
    result = []
    for row in leasing_data + buyout_data:
        item = row_to_dict(row, columns)
        # 轉換日期為字串格式
        if item['date']:
            item['date'] = item['date'].strftime('%Y-%m-%d') if hasattr(item['date'], 'strftime') else str(item['date'])
        if item['end_date']:
            item['end_date'] = item['end_date'].strftime('%Y-%m-%d') if hasattr(item['end_date'], 'strftime') else str(item['end_date'])
        # 確保數值為 float
        item['amount'] = float(item['amount']) if item['amount'] else 0.0
        item['fee'] = float(item['fee']) if item['fee'] else 0.0
        item['received_amount'] = float(item['received_amount']) if item['received_amount'] else 0.0
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
    payable_type: Optional[str] = Query(None, description="付款對象（業務/維護）"),
    contract_type: Optional[str] = Query(None, description="合約類型（租賃/買斷）")
):
    """取得未出帳款（應付帳款 - 未付款），支援多欄位查詢"""
    with get_cursor() as cur:
        result = []
        
        # 查詢租賃合約的未出帳款（業務）
        if not contract_type or contract_type == '租賃':
            if not payable_type or payable_type == '業務':
                where_parts = ["sales_payment_status != '已付款'", "sales_amount > 0"]
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
                    where_parts.append("start_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("start_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("sales_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '租賃' as contract_type,
                        customer_code, customer_name, start_date as date,
                        '業務' as payable_type, sales_company_code as company_code,
                        sales_amount as amount, sales_payment_status as payment_status
                    FROM contracts_leasing
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
        
        # 查詢租賃合約的未出帳款（維護）
        if not contract_type or contract_type == '租賃':
            if not payable_type or payable_type == '維護':
                where_parts = ["service_payment_status != '已付款'", "service_amount > 0"]
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
                    where_parts.append("start_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("start_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("service_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '租賃' as contract_type,
                        customer_code, customer_name, start_date as date,
                        '維護' as payable_type, service_company_code as company_code,
                        service_amount as amount, service_payment_status as payment_status
                    FROM contracts_leasing
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
        
        # 查詢買斷合約的未出帳款（業務）
        if not contract_type or contract_type == '買斷':
            if not payable_type or payable_type == '業務':
                where_parts = ["sales_payment_status != '已付款'", "sales_amount > 0"]
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
                    where_parts.append("deal_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("deal_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("sales_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '買斷' as contract_type,
                        customer_code, customer_name, deal_date as date,
                        '業務' as payable_type, sales_company_code as company_code,
                        sales_amount as amount, sales_payment_status as payment_status
                    FROM contracts_buyout
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
            
            # 查詢買斷合約的未出帳款（維護）
            if not payable_type or payable_type == '維護':
                where_parts = ["service_payment_status != '已付款'", "service_amount > 0"]
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
                    where_parts.append("deal_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("deal_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("service_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '買斷' as contract_type,
                        customer_code, customer_name, deal_date as date,
                        '維護' as payable_type, service_company_code as company_code,
                        service_amount as amount, service_payment_status as payment_status
                    FROM contracts_buyout
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
        
        all_data = result
    
    # 轉換資料
    columns = ['contract_code', 'contract_type', 'customer_code', 'customer_name', 
               'date', 'payable_type', 'company_code', 'amount', 'payment_status']
    
    result = []
    for row in all_data:
        item = row_to_dict(row, columns)
        # 轉換日期為字串格式
        if item['date']:
            item['date'] = item['date'].strftime('%Y-%m-%d') if hasattr(item['date'], 'strftime') else str(item['date'])
        # 確保數值為 float
        item['amount'] = float(item['amount']) if item['amount'] else 0.0
        result.append(item)
    
    return result

@router.get("/payables/paid")
def get_paid_payables(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="付款狀況"),
    payable_type: Optional[str] = Query(None, description="付款對象（業務/維護）"),
    contract_type: Optional[str] = Query(None, description="合約類型（租賃/買斷）")
):
    """取得已出帳款（應付帳款 - 已付款），支援多欄位查詢"""
    with get_cursor() as cur:
        result = []
        
        # 查詢租賃合約的已出帳款（業務）
        if not contract_type or contract_type == '租賃':
            if not payable_type or payable_type == '業務':
                where_parts = ["sales_payment_status = '已付款'", "sales_amount > 0"]
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
                    where_parts.append("start_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("start_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("sales_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '租賃' as contract_type,
                        customer_code, customer_name, start_date as date,
                        '業務' as payable_type, sales_company_code as company_code,
                        sales_amount as amount, sales_payment_status as payment_status
                    FROM contracts_leasing
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
        
        # 查詢租賃合約的已出帳款（維護）
        if not contract_type or contract_type == '租賃':
            if not payable_type or payable_type == '維護':
                where_parts = ["service_payment_status = '已付款'", "service_amount > 0"]
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
                    where_parts.append("start_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("start_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("service_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '租賃' as contract_type,
                        customer_code, customer_name, start_date as date,
                        '維護' as payable_type, service_company_code as company_code,
                        service_amount as amount, service_payment_status as payment_status
                    FROM contracts_leasing
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
        
        # 查詢買斷合約的已出帳款（業務）
        if not contract_type or contract_type == '買斷':
            if not payable_type or payable_type == '業務':
                where_parts = ["sales_payment_status = '已付款'", "sales_amount > 0"]
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
                    where_parts.append("deal_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("deal_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("sales_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '買斷' as contract_type,
                        customer_code, customer_name, deal_date as date,
                        '業務' as payable_type, sales_company_code as company_code,
                        sales_amount as amount, sales_payment_status as payment_status
                    FROM contracts_buyout
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
            
            # 查詢買斷合約的已出帳款（維護）
            if not payable_type or payable_type == '維護':
                where_parts = ["service_payment_status = '已付款'", "service_amount > 0"]
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
                    where_parts.append("deal_date >= %s")
                    params.append(from_date)
                if to_date:
                    where_parts.append("deal_date <= %s")
                    params.append(to_date)
                if payment_status:
                    where_parts.append("service_payment_status = %s")
                    params.append(payment_status)
                
                cur.execute(f"""
                    SELECT 
                        contract_code, '買斷' as contract_type,
                        customer_code, customer_name, deal_date as date,
                        '維護' as payable_type, service_company_code as company_code,
                        service_amount as amount, service_payment_status as payment_status
                    FROM contracts_buyout
                    WHERE {' AND '.join(where_parts)}
                """, tuple(params))
                result.extend(cur.fetchall())
        
        all_data = result
    
    # 轉換資料
    columns = ['contract_code', 'contract_type', 'customer_code', 'customer_name', 
               'date', 'payable_type', 'company_code', 'amount', 'payment_status']
    
    result = []
    for row in all_data:
        item = row_to_dict(row, columns)
        # 轉換日期為字串格式
        if item['date']:
            item['date'] = item['date'].strftime('%Y-%m-%d') if hasattr(item['date'], 'strftime') else str(item['date'])
        # 確保數值為 float
        item['amount'] = float(item['amount']) if item['amount'] else 0.0
        result.append(item)
    
    return result

@router.get("/service")
def get_service_expenses(
    contract_code: Optional[str] = Query(None, description="合約編號（部分比對）"),
    customer_code: Optional[str] = Query(None, description="客戶代碼（部分比對）"),
    customer_name: Optional[str] = Query(None, description="客戶名稱（部分比對）"),
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
    payment_status: Optional[str] = Query(None, description="繳費狀況"),
    service_type: Optional[str] = Query(None, description="服務類型（部分比對）")
):
    """取得服務費用，支援多欄位查詢"""
    with get_cursor() as cur:
        where_parts = []
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
            where_parts.append("service_date >= %s")
            params.append(from_date)
        
        if to_date:
            where_parts.append("service_date <= %s")
            params.append(to_date)
        
        if payment_status:
            where_parts.append("payment_status = %s")
            params.append(payment_status)
        
        if service_type:
            where_parts.append("service_type ILIKE %s")
            params.append(f"%{service_type}%")
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        cur.execute(f"""
            SELECT 
                id, contract_code, customer_code, customer_name,
                service_date, confirm_date, service_type,
                repair_company_code, total_amount, payment_status
            FROM service_expense
            {where_clause}
            ORDER BY service_date DESC
        """, tuple(params))
        rows = cur.fetchall()
    
    # 轉換為字典
    columns = ['id', 'contract_code', 'customer_code', 'customer_name', 
               'service_date', 'confirm_date', 'service_type', 
               'repair_company_code', 'total_amount', 'payment_status']
    
    result = []
    for row in rows:
        item = row_to_dict(row, columns)
        # 轉換日期為字串格式
        if item['service_date']:
            item['service_date'] = item['service_date'].strftime('%Y-%m-%d') if hasattr(item['service_date'], 'strftime') else str(item['service_date'])
        if item['confirm_date']:
            item['confirm_date'] = item['confirm_date'].strftime('%Y-%m-%d') if hasattr(item['confirm_date'], 'strftime') else str(item['confirm_date'])
        # 確保數值為 float
        item['total_amount'] = float(item['total_amount']) if item['total_amount'] else 0.0
        result.append(item)
    
    return result
