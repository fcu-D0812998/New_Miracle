"""合約服務 - 自動生成應收帳款邏輯（重用現有 generate_leasing_ar/generate_buyout_ar）"""
from datetime import date
from app.database import get_connection
from app.utils.date_utils import add_months, subtract_days

def generate_leasing_ar(contract_code: str, customer_code: str, customer_name: str,
                        start_date: date, monthly_rent: float,
                        payment_cycle_months: int, contract_months: int, conn):
    """生成租賃應收帳款 - 重用現有邏輯"""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ar_leasing WHERE contract_code = %s", (contract_code,))
        
        total_periods = contract_months // payment_cycle_months
        remaining_months = contract_months % payment_cycle_months
        current_start = start_date
        
        for _ in range(total_periods):
            current_end = subtract_days(add_months(current_start, payment_cycle_months), 1)
            period_rent = monthly_rent * payment_cycle_months
            
            cur.execute("""
                INSERT INTO ar_leasing 
                (contract_code, customer_code, customer_name, start_date, end_date,
                 total_rent, fee, received_amount, payment_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (contract_code, customer_code, customer_name, current_start, current_end,
                  period_rent, 0, 0, '未收'))
            
            current_start = add_months(current_end, 1)
        
        if remaining_months > 0:
            current_end = subtract_days(add_months(current_start, remaining_months), 1)
            period_rent = monthly_rent * remaining_months
            
            cur.execute("""
                INSERT INTO ar_leasing 
                (contract_code, customer_code, customer_name, start_date, end_date,
                 total_rent, fee, received_amount, payment_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (contract_code, customer_code, customer_name, current_start, current_end,
                  period_rent, 0, 0, '未收'))

def generate_buyout_ar(contract_code: str, customer_code: str, customer_name: str,
                       deal_date: date, deal_amount: float, conn):
    """生成買斷應收帳款 - 重用現有邏輯"""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ar_buyout WHERE contract_code = %s", (contract_code,))
        
        cur.execute("""
            INSERT INTO ar_buyout 
            (contract_code, customer_code, customer_name, deal_date,
             total_amount, fee, received_amount, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (contract_code, customer_code, customer_name, deal_date,
              deal_amount, 0, 0, '未收'))

def generate_service_expenses_for_leasing(contract_code: str, customer_code: str, 
                                          customer_name: str, sales_company_code: str = None,
                                          sales_amount: float = None, service_company_code: str = None,
                                          service_amount: float = None, conn = None):
    """為租賃合約生成服務費用"""
    with conn.cursor() as cur:
        # 取得現有的服務費用
        cur.execute("""
            SELECT id, service_type, total_amount, payment_status
            FROM service_expense
            WHERE contract_code = %s
        """, (contract_code,))
        existing_expenses = cur.fetchall()
        
        existing_sales = None
        existing_service = None
        for exp in existing_expenses:
            exp_id, exp_type, exp_amount, exp_status = exp
            if exp_type == '業務':
                existing_sales = (exp_id, exp_amount, exp_status)
            elif exp_type == '維護':
                existing_service = (exp_id, exp_amount, exp_status)
        
        # 處理業務服務費用
        if sales_company_code and sales_amount and sales_amount > 0:
            if existing_sales:
                # 更新現有服務費用
                exp_id, _, _ = existing_sales
                cur.execute("""
                    UPDATE service_expense
                    SET repair_company_code = %s,
                        total_amount = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (sales_company_code, sales_amount, exp_id))
            else:
                # 新增服務費用
                cur.execute("""
                    INSERT INTO service_expense
                    (contract_code, customer_code, customer_name, service_type,
                     repair_company_code, total_amount, payment_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (contract_code, customer_code, customer_name, '業務',
                      sales_company_code, sales_amount, '未收'))
        else:
            # 刪除業務服務費用（如果存在）
            if existing_sales:
                exp_id, _, _ = existing_sales
                cur.execute("DELETE FROM service_expense WHERE id = %s", (exp_id,))
        
        # 處理維護服務費用
        if service_company_code and service_amount and service_amount > 0:
            if existing_service:
                # 更新現有服務費用
                exp_id, _, _ = existing_service
                cur.execute("""
                    UPDATE service_expense
                    SET repair_company_code = %s,
                        total_amount = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (service_company_code, service_amount, exp_id))
            else:
                # 新增服務費用
                cur.execute("""
                    INSERT INTO service_expense
                    (contract_code, customer_code, customer_name, service_type,
                     repair_company_code, total_amount, payment_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (contract_code, customer_code, customer_name, '維護',
                      service_company_code, service_amount, '未收'))
        else:
            # 刪除維護服務費用（如果存在）
            if existing_service:
                exp_id, _, _ = existing_service
                cur.execute("DELETE FROM service_expense WHERE id = %s", (exp_id,))

def generate_service_expenses_for_buyout(contract_code: str, customer_code: str,
                                        customer_name: str, sales_company_code: str = None,
                                        sales_amount: float = None, service_company_code: str = None,
                                        service_amount: float = None, conn = None):
    """為買斷合約生成服務費用"""
    with conn.cursor() as cur:
        # 取得現有的服務費用
        cur.execute("""
            SELECT id, service_type, total_amount, payment_status
            FROM service_expense
            WHERE contract_code = %s
        """, (contract_code,))
        existing_expenses = cur.fetchall()
        
        existing_sales = None
        existing_service = None
        for exp in existing_expenses:
            exp_id, exp_type, exp_amount, exp_status = exp
            if exp_type == '業務':
                existing_sales = (exp_id, exp_amount, exp_status)
            elif exp_type == '維護':
                existing_service = (exp_id, exp_amount, exp_status)
        
        # 處理業務服務費用
        if sales_company_code and sales_amount and sales_amount > 0:
            if existing_sales:
                # 更新現有服務費用
                exp_id, _, _ = existing_sales
                cur.execute("""
                    UPDATE service_expense
                    SET repair_company_code = %s,
                        total_amount = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (sales_company_code, sales_amount, exp_id))
            else:
                # 新增服務費用
                cur.execute("""
                    INSERT INTO service_expense
                    (contract_code, customer_code, customer_name, service_type,
                     repair_company_code, total_amount, payment_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (contract_code, customer_code, customer_name, '業務',
                      sales_company_code, sales_amount, '未收'))
        else:
            # 刪除業務服務費用（如果存在）
            if existing_sales:
                exp_id, _, _ = existing_sales
                cur.execute("DELETE FROM service_expense WHERE id = %s", (exp_id,))
        
        # 處理維護服務費用
        if service_company_code and service_amount and service_amount > 0:
            if existing_service:
                # 更新現有服務費用
                exp_id, _, _ = existing_service
                cur.execute("""
                    UPDATE service_expense
                    SET repair_company_code = %s,
                        total_amount = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (service_company_code, service_amount, exp_id))
            else:
                # 新增服務費用
                cur.execute("""
                    INSERT INTO service_expense
                    (contract_code, customer_code, customer_name, service_type,
                     repair_company_code, total_amount, payment_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (contract_code, customer_code, customer_name, '維護',
                      service_company_code, service_amount, '未收'))
        else:
            # 刪除維護服務費用（如果存在）
            if existing_service:
                exp_id, _, _ = existing_service
                cur.execute("DELETE FROM service_expense WHERE id = %s", (exp_id,))


