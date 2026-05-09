"""合約服務 - 處理應收帳款與服務費用產生邏輯。"""
from datetime import date
from app.accounting_period import accounting_period_for_date
from app.billing import calculate_receivable_status
from app.utils.date_utils import add_months, subtract_days

RECEIVABLE_UNPAID = "未收"
RECEIVABLE_PARTIAL = "部分收款"
RECEIVABLE_PAID = "已收款"


def _to_float(value) -> float:
    return float(value) if value is not None else 0.0


def _calculate_service_status(amount: float, paid_amount: float) -> str:
    total_due = max(_to_float(amount), 0.0)
    paid = max(_to_float(paid_amount), 0.0)
    if paid >= total_due and total_due > 0:
        return RECEIVABLE_PAID
    if paid > 0:
        return RECEIVABLE_PARTIAL
    return RECEIVABLE_UNPAID


def generate_leasing_ar(contract_code: str, customer_code: str, customer_name: str,
                        start_date: date, monthly_rent: float,
                        payment_cycle_months: int, contract_months: int, conn,
                        needs_invoice: bool = False):
    """產生租賃應收帳款，並盡量保留既有的人工調整與收款資訊。"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT start_date, end_date, fee, received_amount, adjusted_amount
            FROM ar_leasing
            WHERE contract_code = %s
        """, (contract_code,))
        existing_rows = {
            (row[0], row[1]): {
                "fee": _to_float(row[2]),
                "received_amount": _to_float(row[3]),
                "adjusted_amount": float(row[4]) if row[4] is not None else None,
            }
            for row in cur.fetchall()
        }

        cur.execute("DELETE FROM ar_leasing WHERE contract_code = %s", (contract_code,))

        total_periods = contract_months // payment_cycle_months
        remaining_months = contract_months % payment_cycle_months
        current_start = start_date

        def insert_period(period_months: int):
            nonlocal current_start
            current_end = subtract_days(add_months(current_start, period_months), 1)
            base_amount = monthly_rent * period_months
            existing = existing_rows.get((current_start, current_end), {})
            adjusted_amount = existing.get("adjusted_amount")
            fee = existing.get("fee", 0.0)
            received_amount = existing.get("received_amount", 0.0)
            effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
            payment_status = calculate_receivable_status(effective_amount, fee, received_amount, needs_invoice)
            accounting_period = accounting_period_for_date(current_end)

            cur.execute("""
                INSERT INTO ar_leasing
                (contract_code, customer_code, customer_name, start_date, end_date,
                 total_rent, adjusted_amount, fee, received_amount, payment_status, accounting_period)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                contract_code, customer_code, customer_name, current_start, current_end,
                base_amount, adjusted_amount, fee, received_amount, payment_status, accounting_period
            ))

            current_start = add_months(current_start, period_months)

        for _ in range(total_periods):
            insert_period(payment_cycle_months)

        if remaining_months > 0:
            insert_period(remaining_months)


def generate_buyout_ar(contract_code: str, customer_code: str, customer_name: str,
                       deal_date: date, deal_amount: float, conn,
                       needs_invoice: bool = False):
    """產生買斷應收帳款，並保留既有的人工調整與收款資訊。"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT deal_date, fee, received_amount, adjusted_amount
            FROM ar_buyout
            WHERE contract_code = %s
            ORDER BY id
            LIMIT 1
        """, (contract_code,))
        existing = cur.fetchone()

        fee = _to_float(existing[1]) if existing else 0.0
        received_amount = _to_float(existing[2]) if existing else 0.0
        adjusted_amount = float(existing[3]) if existing and existing[3] is not None else None
        effective_amount = adjusted_amount if adjusted_amount is not None else deal_amount
        payment_status = calculate_receivable_status(effective_amount, fee, received_amount, needs_invoice)
        accounting_period = accounting_period_for_date(deal_date)

        cur.execute("DELETE FROM ar_buyout WHERE contract_code = %s", (contract_code,))
        cur.execute("""
            INSERT INTO ar_buyout
            (contract_code, customer_code, customer_name, deal_date,
             total_amount, adjusted_amount, fee, received_amount, payment_status, accounting_period)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            contract_code, customer_code, customer_name, deal_date,
            deal_amount, adjusted_amount, fee, received_amount, payment_status, accounting_period
        ))


def _sync_contract_service_expenses(contract_code: str, customer_code: str, customer_name: str,
                                    sales_company_code: str = None, sales_amount: float = None,
                                    service_company_code: str = None, service_amount: float = None,
                                    conn=None, effective_date: date = None):
    accounting_period = accounting_period_for_date(effective_date)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, service_type, total_amount, adjusted_amount, paid_amount
            FROM service_expense
            WHERE contract_code = %s
              AND COALESCE(expense_source, 'contract') = 'contract'
        """, (contract_code,))
        existing_rows = {
            row[1]: {
                "id": row[0],
                "base_amount": _to_float(row[2]),
                "adjusted_amount": float(row[3]) if row[3] is not None else None,
                "paid_amount": _to_float(row[4]),
            }
            for row in cur.fetchall()
        }

        def upsert(service_type: str, company_code: str, base_amount: float):
            existing = existing_rows.get(service_type)
            if company_code and base_amount and base_amount > 0:
                adjusted_amount = existing["adjusted_amount"] if existing else None
                paid_amount = existing["paid_amount"] if existing else 0.0
                effective_amount = adjusted_amount if adjusted_amount is not None else base_amount
                payment_status = _calculate_service_status(effective_amount, paid_amount)

                if existing:
                    cur.execute("""
                        UPDATE service_expense
                        SET customer_code = %s,
                            customer_name = %s,
                            service_type = %s,
                            repair_company_code = %s,
                            total_amount = %s,
                            adjusted_amount = %s,
                            paid_amount = %s,
                            payment_status = %s,
                            expense_source = 'contract',
                            expense_category = NULL,
                            expense_description = NULL,
                            vendor_name = NULL,
                            accounting_period = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (
                        customer_code, customer_name, service_type, company_code,
                        base_amount, adjusted_amount, paid_amount, payment_status, accounting_period,
                        existing["id"]
                    ))
                else:
                    cur.execute("""
                        INSERT INTO service_expense
                        (contract_code, customer_code, customer_name, service_type,
                         repair_company_code, total_amount, adjusted_amount, paid_amount,
                         payment_status, expense_source, accounting_period)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'contract', %s)
                    """, (
                        contract_code, customer_code, customer_name, service_type,
                        company_code, base_amount, None, 0, RECEIVABLE_UNPAID, accounting_period
                    ))
            elif existing:
                cur.execute("DELETE FROM service_expense WHERE id = %s", (existing["id"],))

        upsert("業務", sales_company_code, sales_amount)
        upsert("維護", service_company_code, service_amount)


def generate_service_expenses_for_leasing(contract_code: str, customer_code: str,
                                          customer_name: str, sales_company_code: str = None,
                                          sales_amount: float = None, service_company_code: str = None,
                                          service_amount: float = None, conn=None,
                                          effective_date: date = None):
    """同步租賃合約的業務/維護服務費用。"""
    _sync_contract_service_expenses(
        contract_code,
        customer_code,
        customer_name,
        sales_company_code=sales_company_code,
        sales_amount=sales_amount,
        service_company_code=service_company_code,
        service_amount=service_amount,
        conn=conn,
        effective_date=effective_date,
    )


def generate_service_expenses_for_buyout(contract_code: str, customer_code: str,
                                         customer_name: str, sales_company_code: str = None,
                                         sales_amount: float = None, service_company_code: str = None,
                                         service_amount: float = None, conn=None,
                                         effective_date: date = None):
    """同步買斷合約的業務/維護服務費用。"""
    _sync_contract_service_expenses(
        contract_code,
        customer_code,
        customer_name,
        sales_company_code=sales_company_code,
        sales_amount=sales_amount,
        service_company_code=service_company_code,
        service_amount=service_amount,
        conn=conn,
        effective_date=effective_date,
    )
