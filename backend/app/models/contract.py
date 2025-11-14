"""合約資料模型 - 統一處理租賃/買斷"""
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import date, datetime

class ContractLeasingBase(BaseModel):
    contract_code: str
    customer_code: str
    start_date: date
    model: Optional[str] = None
    quantity: int = 1
    monthly_rent: Optional[float] = None
    payment_cycle_months: int = 1
    overprint: Optional[str] = None
    contract_months: Optional[int] = None
    sales_company_code: Optional[str] = None
    sales_amount: Optional[float] = None
    service_company_code: Optional[str] = None
    service_amount: Optional[float] = None
    needs_invoice: bool = False

class ContractBuyoutBase(BaseModel):
    contract_code: str
    customer_code: str
    deal_date: date
    deal_amount: Optional[float] = None
    sales_company_code: Optional[str] = None
    sales_amount: Optional[float] = None
    service_company_code: Optional[str] = None
    service_amount: Optional[float] = None
    needs_invoice: bool = False

class ContractLeasingCreate(ContractLeasingBase):
    pass

class ContractBuyoutCreate(ContractBuyoutBase):
    pass

class ContractLeasing(ContractLeasingBase):
    id: int
    customer_name: Optional[str] = None
    sales_payment_status: str = "未付款"
    service_payment_status: str = "未付款"
    status: str = "active"
    needs_invoice: bool = False
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ContractBuyout(ContractBuyoutBase):
    id: int
    customer_name: Optional[str] = None
    sales_payment_status: str = "未付款"
    service_payment_status: str = "未付款"
    status: str = "active"
    needs_invoice: bool = False
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ContractResume(BaseModel):
    resume_date: Optional[date] = None


