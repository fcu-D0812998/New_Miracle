# Backend startup script (PowerShell)
# Environment variables are loaded from .env file automatically by config.py
# For local development: Create .env file from .env.example
# For Render: Set environment variables in Render Dashboard

Write-Host "Starting FastAPI backend server..." -ForegroundColor Green
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path .env)) {
    Write-Host "Warning: .env file not found!" -ForegroundColor Yellow
    Write-Host "Please create .env file from .env.example and fill in your database credentials" -ForegroundColor Yellow
    Write-Host ""
}

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
