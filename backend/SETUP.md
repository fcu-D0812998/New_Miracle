# 本地開發設定指南

## 第一次設定

1. **建立環境變數檔案**
   ```powershell
   # 複製範本
   Copy-Item .env.example .env
   ```

2. **編輯 `.env` 檔案**
   使用文字編輯器開啟 `backend/.env`，填入真實的資料庫連線資訊：
   ```
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_HOST=your_db_host
   DB_NAME=your_db_name
   DB_PORT=5432
   DB_SSLMODE=require
   ```

3. **啟動後端**
   ```powershell
   .\start.ps1
   ```

## 重要提醒

- ⚠️ `.env` 檔案包含敏感資訊，**絕對不要**推送到 Git
- ✅ `.env.example` 是範本，可以安全推送
- ✅ `.env` 檔案已加入 `.gitignore`，不會被意外推送

