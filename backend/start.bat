@echo off
REM Backend startup script (Windows Batch)
REM Environment variables are loaded from .env file automatically by config.py
REM For local development: Create .env file from .env.example
REM For Render: Set environment variables in Render Dashboard

echo Starting FastAPI backend server...
echo API Docs: http://localhost:8000/docs
echo Press Ctrl+C to stop the server
echo.

if not exist .env (
    echo Warning: .env file not found!
    echo Please create .env file from .env.example and fill in your database credentials
    echo.
)

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
