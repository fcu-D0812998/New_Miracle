"""銀行帳本 API - 暫時最小實作，讓後端能啟動"""
from fastapi import APIRouter

router = APIRouter()

@router.get("")
def get_bank_ledger():
    """取得銀行帳本 - 待實作"""
    return []

