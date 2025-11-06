"""公司資料 API"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.database import get_cursor
from app.models.company import Company, CompanyCreate, CompanyUpdate

router = APIRouter()

@router.get("", response_model=List[Company])
def get_companies(
    type: Optional[str] = Query(None, description="篩選類型: sales 或 service"),
    search: Optional[str] = Query(None, description="搜尋關鍵字")
):
    """取得公司列表"""
    with get_cursor() as cur:
        query = """
            SELECT id, company_code, name, contact_name, mobile, phone,
                   address, email, tax_id, sales_rep, is_sales, is_service,
                   created_at, updated_at
            FROM companies
            WHERE 1=1
        """
        params = []
        
        if type == "sales":
            query += " AND is_sales = TRUE"
        elif type == "service":
            query += " AND is_service = TRUE"
        
        if search:
            query += """ AND (company_code ILIKE %s OR name ILIKE %s
                             OR contact_name ILIKE %s OR mobile ILIKE %s)"""
            params.extend([f"%{search}%"] * 4)
        
        query += " ORDER BY name"
        cur.execute(query, params)
        rows = cur.fetchall()
    
    return [
        Company(
            id=r[0], company_code=r[1], name=r[2], contact_name=r[3],
            mobile=r[4], phone=r[5], address=r[6], email=r[7],
            tax_id=r[8], sales_rep=r[9], is_sales=r[10], is_service=r[11],
            created_at=r[12], updated_at=r[13]
        ) for r in rows
    ]

@router.get("/{company_code}", response_model=Company)
def get_company(company_code: str):
    """取得單一公司"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, company_code, name, contact_name, mobile, phone,
                   address, email, tax_id, sales_rep, is_sales, is_service,
                   created_at, updated_at
            FROM companies
            WHERE company_code = %s
        """, (company_code,))
        row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="公司不存在")
    
    return Company(
        id=row[0], company_code=row[1], name=row[2], contact_name=row[3],
        mobile=row[4], phone=row[5], address=row[6], email=row[7],
        tax_id=row[8], sales_rep=row[9], is_sales=row[10], is_service=row[11],
        created_at=row[12], updated_at=row[13]
    )

@router.post("", response_model=Company, status_code=201)
def create_company(company: CompanyCreate):
    """新增公司"""
    with get_cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO companies 
                (company_code, name, contact_name, mobile, phone, address,
                 email, tax_id, sales_rep, is_sales, is_service)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at, updated_at
            """, (
                company.company_code, company.name, company.contact_name,
                company.mobile, company.phone, company.address,
                company.email, company.tax_id, company.sales_rep,
                company.is_sales, company.is_service
            ))
            row = cur.fetchone()
            return Company(
                id=row[0], company_code=company.company_code,
                name=company.name, contact_name=company.contact_name,
                mobile=company.mobile, phone=company.phone,
                address=company.address, email=company.email,
                tax_id=company.tax_id, sales_rep=company.sales_rep,
                is_sales=company.is_sales, is_service=company.is_service,
                created_at=row[1], updated_at=row[2]
            )
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(status_code=400, detail="公司代碼已存在")
            raise HTTPException(status_code=500, detail=str(e))

@router.put("/{company_code}", response_model=Company)
def update_company(company_code: str, company: CompanyUpdate):
    """更新公司"""
    with get_cursor() as cur:
        cur.execute("""
            UPDATE companies
            SET name = %s, contact_name = %s, mobile = %s, phone = %s,
                address = %s, email = %s, tax_id = %s, sales_rep = %s,
                is_sales = %s, is_service = %s, updated_at = CURRENT_TIMESTAMP
            WHERE company_code = %s
            RETURNING id, created_at, updated_at
        """, (
            company.name, company.contact_name, company.mobile,
            company.phone, company.address, company.email,
            company.tax_id, company.sales_rep, company.is_sales,
            company.is_service, company_code
        ))
        row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="公司不存在")
    
    return Company(
        id=row[0], company_code=company_code, name=company.name,
        contact_name=company.contact_name, mobile=company.mobile,
        phone=company.phone, address=company.address,
        email=company.email, tax_id=company.tax_id,
        sales_rep=company.sales_rep, is_sales=company.is_sales,
        is_service=company.is_service, created_at=row[1], updated_at=row[2]
    )

@router.delete("/{company_code}", status_code=204)
def delete_company(company_code: str):
    """刪除公司"""
    with get_cursor() as cur:
        cur.execute("DELETE FROM companies WHERE company_code = %s", (company_code,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="公司不存在")


