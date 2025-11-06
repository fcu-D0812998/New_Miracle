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


