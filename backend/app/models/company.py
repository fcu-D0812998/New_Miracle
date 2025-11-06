"""公司資料模型"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CompanyBase(BaseModel):
    company_code: str
    name: str
    contact_name: Optional[str] = None
    mobile: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    tax_id: Optional[str] = None
    sales_rep: Optional[str] = None
    is_sales: bool = False
    is_service: bool = False

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    mobile: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    tax_id: Optional[str] = None
    sales_rep: Optional[str] = None
    is_sales: bool = False
    is_service: bool = False

class Company(CompanyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


