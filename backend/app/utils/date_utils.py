"""日期工具 - 重用現有邏輯"""
from dateutil.relativedelta import relativedelta
from datetime import date

def add_months(start_date: date, months: int) -> date:
    """加月數"""
    return start_date + relativedelta(months=months)

def subtract_days(target_date: date, days: int) -> date:
    """減天數"""
    return target_date - relativedelta(days=days)


