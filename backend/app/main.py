"""FastAPI 應用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import customers, companies, contracts, accounts, bank_ledger

app = FastAPI(title="印表機記帳平台 API", version="1.0.0")

# CORS 設定（允許前端連接）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 本地開發環境 (Vite)
        "http://localhost:5173",  # 本地開發環境 (Vite 預設)
        "http://127.0.0.1:3000",  # 本地開發環境 (localhost 別名)
        "http://127.0.0.1:5173",  # 本地開發環境 (localhost 別名)
        "https://miracle-frontend.onrender.com",  # 生產環境前端
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(customers.router, prefix="/api/customers", tags=["customers"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(bank_ledger.router, prefix="/api/bank-ledger", tags=["bank-ledger"])

@app.get("/")
def root():
    return {"message": "印表機記帳平台 API"}

@app.get("/health")
def health():
    return {"status": "ok"}


