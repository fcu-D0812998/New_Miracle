# Miracle 記帳系統後端 API

FastAPI 後端，對應前端 React 應用。

## 環境設定

### 本地開發

1. 複製環境變數範本：
   ```bash
   cp .env.example .env
   ```

2. 編輯 `.env` 檔案，填入真實的資料庫連線資訊：
   ```
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_HOST=your_db_host
   DB_NAME=your_db_name
   DB_PORT=5432
   DB_SSLMODE=require
   ```

3. 啟動伺服器：
   ```bash
   # PowerShell
   .\start.ps1
   
   # 或 CMD
   start.bat
   
   # 或手動執行
   uvicorn app.main:app --reload
   ```

### Render 部署

1. 在 Render Dashboard → Environment 設定以下環境變數：
   - `DB_USER`
   - `DB_PASSWORD`
   - `DB_HOST`
   - `DB_NAME`
   - `DB_PORT` (預設: 5432)
   - `DB_SSLMODE` (預設: require)

2. Render 會自動執行 `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. 不需要 `.env` 檔案，環境變數會從 Render Dashboard 讀取

## API 文檔

啟動後訪問：`http://localhost:8000/docs`

## API 端點

- `/api/customers` - 客戶資料管理
- `/api/companies` - 公司資料管理
- `/api/contracts/leasing` - 租賃合約
- `/api/contracts/buyout` - 買斷合約
- `/api/accounts/*` - 帳款查詢
- `/api/bank-ledger` - 銀行帳本

## 安全注意事項

- ⚠️ `.env` 檔案包含敏感資訊，**不要**推送到 Git
- ✅ `.env.example` 是範本檔案，可以安全推送
- ✅ Render 部署時，在 Dashboard 手動設定環境變數
