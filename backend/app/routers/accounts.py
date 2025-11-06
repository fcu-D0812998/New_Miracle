"""帳款查詢 API - 暫時最小實作，讓後端能啟動"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/receivables")
def get_receivables():
    """取得應收帳款 - 待實作"""
    return []

@router.get("/payables/unpaid")
def get_unpaid_payables():
    """取得未出帳款 - 待實作"""
    return []

@router.get("/payables/paid")
def get_paid_payables():
    """取得已出帳款 - 待實作"""
    return []

@router.get("/service")
def get_service_expenses():
    """取得服務費用 - 待實作"""
    return []

