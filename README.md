# 印表機記帳平台

React 18 + Ant Design 前端 + FastAPI 後端

## 專案結構

```
react/
├── src/              # 前端 React 應用
│   ├── pages/        # 頁面組件
│   ├── services/     # API Service 層
│   └── ...
└── backend/          # 後端 FastAPI 應用
    ├── app/
    │   ├── routers/  # API 路由
    │   ├── models/   # 資料模型
    │   └── services/ # 業務邏輯
    └── ...
```

## 快速開始

### 1. 啟動後端

```powershell
cd backend
.\start.ps1
```

或手動設定環境變數後執行：
```powershell
$env:DB_USER="your_db_user"
$env:DB_PASSWORD="your_db_password"
$env:DB_HOST="your_db_host"
$env:DB_NAME="your_db_name"
$env:DB_PORT="5432"
$env:DB_SSLMODE="require"

uvicorn app.main:app --reload
```

後端將在 `http://localhost:8000` 啟動
API 文檔：`http://localhost:8000/docs`

### 2. 啟動前端

```powershell
cd react  # 或回到專案根目錄
npm install  # 如果還沒安裝依賴
npm run dev
```

前端將在 `http://localhost:5173` 啟動（Vite 預設）

### 3. 環境變數設定

前端需要設定 API URL（可選，預設為 `http://localhost:8000/api`）：

建立 `.env` 檔案：
```
VITE_API_URL=http://localhost:8000/api
```

## 功能模組

- ✅ 客戶資料管理 - CRUD、搜尋
- ✅ 公司資料管理 - CRUD、搜尋、類型篩選
- ✅ 合約管理 - 租賃/買斷合約、自動生成應收帳款
- ⚠️ 帳款查詢 - 前端已連接，後端 API 待實作完整
- ⚠️ 銀行帳本 - 前端已連接，後端 API 待實作完整

## 技術棧

### 前端
- React 18
- Ant Design 5
- React Router 6
- Axios
- Vite

### 後端
- FastAPI
- PostgreSQL (Neon)
- psycopg 3

## 部署

### Render 部署

後端：使用 `render.yaml` 配置，設定環境變數即可
前端：Static Site，Build Command: `npm run build`，Publish Directory: `dist`

## 注意事項

1. 後端需要設定環境變數才能連接資料庫
2. 前端預設連接到 `http://localhost:8000/api`，可透過 `.env` 修改
3. 帳款查詢和銀行帳本的完整 API 功能待實作
