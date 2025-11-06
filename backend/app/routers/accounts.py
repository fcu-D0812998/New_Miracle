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
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)")
):
    """取得總應收帳款（合併租賃和買斷）"""
    with get_cursor() as cur:
        # 查詢租賃應收帳款
        if from_date and to_date:
            cur.execute("""
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
                WHERE start_date BETWEEN %s AND %s
                ORDER BY contract_code
            """, (from_date, to_date))
        else:
            cur.execute("""
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
                ORDER BY contract_code
            """)
        leasing_data = cur.fetchall()
        
        # 查詢買斷應收帳款
        if from_date and to_date:
            cur.execute("""
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
                WHERE deal_date BETWEEN %s AND %s
                ORDER BY contract_code
            """, (from_date, to_date))
        else:
            cur.execute("""
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
                ORDER BY contract_code
            """)
        buyout_data = cur.fetchall()
    
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
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)")
):
    """取得未出帳款（應付帳款 - 未付款）"""
    with get_cursor() as cur:
        # 查詢租賃合約的未出帳款（業務）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_leasing
                WHERE start_date BETWEEN %s AND %s
                  AND sales_payment_status != '已付款'
                  AND sales_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_leasing
                WHERE sales_payment_status != '已付款'
                  AND sales_amount > 0
            """)
        leasing_sales = cur.fetchall()
        
        # 查詢租賃合約的未出帳款（維護）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_leasing
                WHERE start_date BETWEEN %s AND %s
                  AND service_payment_status != '已付款'
                  AND service_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_leasing
                WHERE service_payment_status != '已付款'
                  AND service_amount > 0
            """)
        leasing_service = cur.fetchall()
        
        # 查詢買斷合約的未出帳款（業務）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_buyout
                WHERE deal_date BETWEEN %s AND %s
                  AND sales_payment_status != '已付款'
                  AND sales_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_buyout
                WHERE sales_payment_status != '已付款'
                  AND sales_amount > 0
            """)
        buyout_sales = cur.fetchall()
        
        # 查詢買斷合約的未出帳款（維護）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_buyout
                WHERE deal_date BETWEEN %s AND %s
                  AND service_payment_status != '已付款'
                  AND service_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_buyout
                WHERE service_payment_status != '已付款'
                  AND service_amount > 0
            """)
        buyout_service = cur.fetchall()
    
    # 合併所有資料
    columns = ['contract_code', 'contract_type', 'customer_code', 'customer_name', 
               'date', 'payable_type', 'company_code', 'amount', 'payment_status']
    
    result = []
    for row in leasing_sales + leasing_service + buyout_sales + buyout_service:
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
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)")
):
    """取得已出帳款（應付帳款 - 已付款）"""
    with get_cursor() as cur:
        # 查詢租賃合約的已出帳款（業務）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_leasing
                WHERE start_date BETWEEN %s AND %s
                  AND sales_payment_status = '已付款'
                  AND sales_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_leasing
                WHERE sales_payment_status = '已付款'
                  AND sales_amount > 0
            """)
        leasing_sales = cur.fetchall()
        
        # 查詢租賃合約的已出帳款（維護）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_leasing
                WHERE start_date BETWEEN %s AND %s
                  AND service_payment_status = '已付款'
                  AND service_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '租賃' as contract_type,
                    customer_code,
                    customer_name,
                    start_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_leasing
                WHERE service_payment_status = '已付款'
                  AND service_amount > 0
            """)
        leasing_service = cur.fetchall()
        
        # 查詢買斷合約的已出帳款（業務）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_buyout
                WHERE deal_date BETWEEN %s AND %s
                  AND sales_payment_status = '已付款'
                  AND sales_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '業務' as payable_type,
                    sales_company_code as company_code,
                    sales_amount as amount,
                    sales_payment_status as payment_status
                FROM contracts_buyout
                WHERE sales_payment_status = '已付款'
                  AND sales_amount > 0
            """)
        buyout_sales = cur.fetchall()
        
        # 查詢買斷合約的已出帳款（維護）
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_buyout
                WHERE deal_date BETWEEN %s AND %s
                  AND service_payment_status = '已付款'
                  AND service_amount > 0
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    contract_code,
                    '買斷' as contract_type,
                    customer_code,
                    customer_name,
                    deal_date as date,
                    '維護' as payable_type,
                    service_company_code as company_code,
                    service_amount as amount,
                    service_payment_status as payment_status
                FROM contracts_buyout
                WHERE service_payment_status = '已付款'
                  AND service_amount > 0
            """)
        buyout_service = cur.fetchall()
    
    # 合併所有資料
    columns = ['contract_code', 'contract_type', 'customer_code', 'customer_name', 
               'date', 'payable_type', 'company_code', 'amount', 'payment_status']
    
    result = []
    for row in leasing_sales + leasing_service + buyout_sales + buyout_service:
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
    from_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)")
):
    """取得服務費用"""
    with get_cursor() as cur:
        if from_date and to_date:
            cur.execute("""
                SELECT 
                    id,
                    contract_code,
                    customer_code,
                    customer_name,
                    service_date,
                    confirm_date,
                    service_type,
                    repair_company_code,
                    total_amount,
                    payment_status
                FROM service_expense
                WHERE service_date BETWEEN %s AND %s
                ORDER BY service_date DESC
            """, (from_date, to_date))
        else:
            cur.execute("""
                SELECT 
                    id,
                    contract_code,
                    customer_code,
                    customer_name,
                    service_date,
                    confirm_date,
                    service_type,
                    repair_company_code,
                    total_amount,
                    payment_status
                FROM service_expense
                ORDER BY service_date DESC
            """)
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
