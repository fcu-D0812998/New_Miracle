"""帳務期間工具。

2026-01-01 以前的資料視為前帳；預設查詢只顯示本期資料。
"""
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException

from app.utils.date_utils import add_months, subtract_days

ACCOUNTING_CUTOFF_DATE = date(2026, 1, 1)
ACCOUNTING_CURRENT = "current"
ACCOUNTING_PRIOR = "prior"
ACCOUNTING_ALL = "all"


def normalize_accounting_period(value: Optional[str] = None) -> str:
    """正規化前端/API 傳入的帳務期間。"""
    normalized = (value or ACCOUNTING_CURRENT).strip().lower()
    mapping = {
        "current": ACCOUNTING_CURRENT,
        "本期": ACCOUNTING_CURRENT,
        "prior": ACCOUNTING_PRIOR,
        "previous": ACCOUNTING_PRIOR,
        "前帳": ACCOUNTING_PRIOR,
        "all": ACCOUNTING_ALL,
        "全部": ACCOUNTING_ALL,
    }
    if normalized not in mapping:
        raise HTTPException(status_code=400, detail="帳務期間參數錯誤")
    return mapping[normalized]


def apply_accounting_period_filter(where_parts: list, params: list,
                                   column: str = "accounting_period",
                                   value: Optional[str] = None) -> str:
    """把帳務期間條件加入 SQL where_parts。"""
    normalized = normalize_accounting_period(value)
    if normalized != ACCOUNTING_ALL:
        where_parts.append(f"COALESCE({column}, %s) = %s")
        params.extend([ACCOUNTING_CURRENT, normalized])
    return normalized


def accounting_period_for_date(value) -> str:
    """依日期判斷本期或前帳。"""
    if isinstance(value, datetime):
        value = value.date()
    return ACCOUNTING_PRIOR if value and value < ACCOUNTING_CUTOFF_DATE else ACCOUNTING_CURRENT


def leasing_contract_end_date(start_date: Optional[date], contract_months: Optional[int]) -> Optional[date]:
    """租賃合約的有效結束日。"""
    if not start_date:
        return None
    if not contract_months or contract_months <= 0:
        return start_date
    return subtract_days(add_months(start_date, contract_months), 1)
