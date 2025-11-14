"""客戶資料模型"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CustomerBase(BaseModel):
    customer_code: str
    name: str
    contact_name: Optional[str] = None
    mobile: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    tax_id: Optional[str] = None
    sales_rep_name: Optional[str] = None
    remark: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    mobile: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    tax_id: Optional[str] = None
    sales_rep_name: Optional[str] = None
    remark: Optional[str] = None

class Customer(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CustomerCodeChange(BaseModel):
    new_customer_code: str


