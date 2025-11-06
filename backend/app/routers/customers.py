"""客戶資料 API - 簡潔直接，不要廢話"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.database import get_cursor
from app.models.customer import Customer, CustomerCreate, CustomerUpdate

router = APIRouter()

@router.get("", response_model=List[Customer])
def get_customers(search: Optional[str] = Query(None, description="搜尋關鍵字")):
    """取得客戶列表（支援搜尋）"""
    with get_cursor() as cur:
        if search:
            cur.execute("""
                SELECT id, customer_code, name, contact_name, mobile, phone,
                       address, email, tax_id, sales_rep_name, remark,
                       created_at, updated_at
                FROM customers
                WHERE customer_code ILIKE %s OR name ILIKE %s 
                   OR contact_name ILIKE %s OR mobile ILIKE %s
                   OR phone ILIKE %s OR email ILIKE %s
                ORDER BY customer_code
            """, (f"%{search}%",) * 6)
        else:
            cur.execute("""
                SELECT id, customer_code, name, contact_name, mobile, phone,
                       address, email, tax_id, sales_rep_name, remark,
                       created_at, updated_at
                FROM customers
                ORDER BY customer_code
            """)
        rows = cur.fetchall()
    
    return [
        Customer(
            id=r[0], customer_code=r[1], name=r[2], contact_name=r[3],
            mobile=r[4], phone=r[5], address=r[6], email=r[7],
            tax_id=r[8], sales_rep_name=r[9], remark=r[10],
            created_at=r[11], updated_at=r[12]
        ) for r in rows
    ]

@router.get("/{customer_code}", response_model=Customer)
def get_customer(customer_code: str):
    """取得單一客戶"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, customer_code, name, contact_name, mobile, phone,
                   address, email, tax_id, sales_rep_name, remark,
                   created_at, updated_at
            FROM customers
            WHERE customer_code = %s
        """, (customer_code,))
        row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="客戶不存在")
    
    return Customer(
        id=row[0], customer_code=row[1], name=row[2], contact_name=row[3],
        mobile=row[4], phone=row[5], address=row[6], email=row[7],
        tax_id=row[8], sales_rep_name=row[9], remark=row[10],
        created_at=row[11], updated_at=row[12]
    )

@router.post("", response_model=Customer, status_code=201)
def create_customer(customer: CustomerCreate):
    """新增客戶"""
    with get_cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO customers 
                (customer_code, name, contact_name, mobile, phone, address,
                 email, tax_id, sales_rep_name, remark)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at, updated_at
            """, (
                customer.customer_code, customer.name, customer.contact_name,
                customer.mobile, customer.phone, customer.address,
                customer.email, customer.tax_id, customer.sales_rep_name,
                customer.remark
            ))
            row = cur.fetchone()
            return Customer(
                id=row[0], customer_code=customer.customer_code,
                name=customer.name, contact_name=customer.contact_name,
                mobile=customer.mobile, phone=customer.phone,
                address=customer.address, email=customer.email,
                tax_id=customer.tax_id, sales_rep_name=customer.sales_rep_name,
                remark=customer.remark, created_at=row[1], updated_at=row[2]
            )
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(status_code=400, detail="客戶代碼已存在")
            raise HTTPException(status_code=500, detail=str(e))

@router.put("/{customer_code}", response_model=Customer)
def update_customer(customer_code: str, customer: CustomerUpdate):
    """更新客戶"""
    with get_cursor() as cur:
        cur.execute("""
            UPDATE customers
            SET name = %s, contact_name = %s, mobile = %s, phone = %s,
                address = %s, email = %s, tax_id = %s,
                sales_rep_name = %s, remark = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE customer_code = %s
            RETURNING id, created_at, updated_at
        """, (
            customer.name, customer.contact_name, customer.mobile,
            customer.phone, customer.address, customer.email,
            customer.tax_id, customer.sales_rep_name, customer.remark,
            customer_code
        ))
        row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="客戶不存在")
    
    return Customer(
        id=row[0], customer_code=customer_code, name=customer.name,
        contact_name=customer.contact_name, mobile=customer.mobile,
        phone=customer.phone, address=customer.address,
        email=customer.email, tax_id=customer.tax_id,
        sales_rep_name=customer.sales_rep_name, remark=customer.remark,
        created_at=row[1], updated_at=row[2]
    )

@router.delete("/{customer_code}", status_code=204)
def delete_customer(customer_code: str):
    """刪除客戶"""
    with get_cursor() as cur:
        cur.execute("DELETE FROM customers WHERE customer_code = %s", (customer_code,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="客戶不存在")


