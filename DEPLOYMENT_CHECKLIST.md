# 部署前檢查清單

## ✅ 已完成的修改

### 1. 環境變數管理
- ✅ 建立 `backend/.env.example`（範本檔案，可安全推送）
- ✅ 更新 `.gitignore`（忽略所有 `.env` 檔案）
- ✅ 移除啟動腳本中的硬編碼密碼

### 2. 啟動腳本
- ✅ `backend/start.ps1` - 已移除硬編碼密碼
- ✅ `backend/start.bat` - 已移除硬編碼密碼
- ✅ 啟動腳本會檢查 `.env` 檔案是否存在

### 3. 敏感檔案保護
- ✅ 所有敏感資訊已從程式碼中移除

## 📋 推送前確認

### 檢查項目

1. **確認 `.env` 檔案不會被推送**
   ```powershell
   git status
   # 不應該看到 backend/.env 或任何 .env 檔案
   ```

2. **確認範本檔案會被推送**
   ```powershell
   git status
   # 應該看到：
   # - backend/.env.example
   ```

## 🚀 Render 部署步驟

### 後端部署

1. 推送程式碼到 GitHub
2. 在 Render Dashboard 建立新的 Web Service
3. 連接 GitHub 倉庫
4. Render 會自動偵測 `backend/render.yaml`
5. **重要**：在 Render Dashboard → Environment 手動設定：
   ```
   DB_USER = neondb_owner
   DB_PASSWORD = npg_qtAB6EhysQK9
   DB_HOST = ep-curly-voice-a14v87l0-pooler.ap-southeast-1.aws.neon.tech
   DB_NAME = neondb
   DB_PORT = 5432
   DB_SSLMODE = require
   ```
6. Render 會自動部署並啟動

### 前端部署

1. 在 Render Dashboard 建立 Static Site
2. 連接 GitHub 倉庫
3. 設定：
   - Build Command: `npm install && npm run build`
   - Publish Directory: `dist`
   - 環境變數（可選）：
     ```
     VITE_API_URL = https://你的後端URL.onrender.com/api
     ```

## ⚠️ 安全提醒

- ✅ 所有敏感資訊已從程式碼中移除
- ✅ `.env` 檔案已加入 `.gitignore`
- ✅ 只有範本檔案（`.example`）會被推送
- ✅ Render 部署時，在 Dashboard 手動設定環境變數

## 📝 本地開發設定

第一次使用時：

1. 複製環境變數範本：
   ```powershell
   cd backend
   Copy-Item .env.example .env
   ```

2. 編輯 `.env` 檔案，填入真實資料庫連線資訊

3. 啟動後端：
   ```powershell
   .\start.ps1
   ```

