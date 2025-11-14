"""客戶資料 API - 簡潔直接，不要廢話"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.database import get_cursor, get_connection
from app.models.customer import Customer, CustomerCreate, CustomerUpdate, CustomerCodeChange

router = APIRouter()

def _row_to_customer(row) -> Customer:
    return Customer(
        id=row[0], customer_code=row[1], name=row[2], contact_name=row[3],
        mobile=row[4], phone=row[5], address=row[6], email=row[7],
        tax_id=row[8], sales_rep_name=row[9], remark=row[10],
        created_at=row[11], updated_at=row[12]
    )

def _fetch_customer(cur, customer_code: str, for_update: bool = False):
    sql = """
        SELECT id, customer_code, name, contact_name, mobile, phone,
               address, email, tax_id, sales_rep_name, remark,
               created_at, updated_at
        FROM customers
        WHERE customer_code = %s
    """
    if for_update:
        sql += " FOR UPDATE"
    cur.execute(sql, (customer_code,))
    return cur.fetchone()

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
    
    return [_row_to_customer(r) for r in rows]

@router.get("/{customer_code}", response_model=Customer)
def get_customer(customer_code: str):
    """取得單一客戶"""
    with get_cursor() as cur:
        row = _fetch_customer(cur, customer_code)
    
    if not row:
        raise HTTPException(status_code=404, detail="客戶不存在")
    
    return _row_to_customer(row)

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
                RETURNING id
            """, (
                customer.customer_code, customer.name, customer.contact_name,
                customer.mobile, customer.phone, customer.address,
                customer.email, customer.tax_id, customer.sales_rep_name,
                customer.remark
            ))
            row = cur.fetchone()
            full_row = _fetch_customer(cur, customer.customer_code)
            return _row_to_customer(full_row)
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
            RETURNING id
        """, (
            customer.name, customer.contact_name, customer.mobile,
            customer.phone, customer.address, customer.email,
            customer.tax_id, customer.sales_rep_name, customer.remark,
            customer_code
        ))
        row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="客戶不存在")
    
    with get_cursor() as cur:
        refreshed = _fetch_customer(cur, customer_code)
    
    if not refreshed:
        raise HTTPException(status_code=500, detail="客戶讀取失敗")
    
    return _row_to_customer(refreshed)


@router.post("/{customer_code}/change-code", response_model=Customer)
def change_customer_code(customer_code: str, payload: CustomerCodeChange):
    """更換客戶代碼並同步所有關聯資料"""
    new_code = payload.new_customer_code.strip()
    if not new_code:
        raise HTTPException(status_code=400, detail="新客戶代碼不得為空")
    if new_code == customer_code:
        return get_customer(customer_code)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            current = _fetch_customer(cur, customer_code, for_update=True)
            if not current:
                raise HTTPException(status_code=404, detail="客戶不存在")

            cur.execute(
                "SELECT 1 FROM customers WHERE customer_code = %s",
                (new_code,)
            )
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="新客戶代碼已存在")

            for sql in (
                "UPDATE contracts_leasing SET customer_code = %s WHERE customer_code = %s",
                "UPDATE contracts_buyout SET customer_code = %s WHERE customer_code = %s",
                "UPDATE ar_leasing SET customer_code = %s WHERE customer_code = %s",
                "UPDATE ar_buyout SET customer_code = %s WHERE customer_code = %s",
                "UPDATE service_expense SET customer_code = %s WHERE customer_code = %s"
            ):
                cur.execute(sql, (new_code, customer_code))

            cur.execute("""
                UPDATE customers
                SET customer_code = %s, updated_at = CURRENT_TIMESTAMP
                WHERE customer_code = %s
            """, (new_code, customer_code))

            conn.commit()

            refreshed = _fetch_customer(cur, new_code)
            if not refreshed:
                raise HTTPException(status_code=500, detail="客戶讀取失敗")
            return _row_to_customer(refreshed)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/{customer_code}", status_code=204)
def delete_customer(customer_code: str):
    """刪除客戶"""
    with get_cursor() as cur:
        cur.execute("DELETE FROM customers WHERE customer_code = %s", (customer_code,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="客戶不存在")


