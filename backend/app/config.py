"""資料庫配置 - 從環境變數讀取，重用現有 db_config.py 邏輯"""
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    user: str
    password: str
    host: str
    name: str
    port: str = "5432"
    sslmode: str = "require"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "DB_"

def get_db_config():
    """取得資料庫連線設定 - 重用現有邏輯"""
    settings = Settings()
    return {
        'host': settings.host,
        'dbname': settings.name,
        'user': settings.user,
        'password': settings.password,
        'port': settings.port,
        'sslmode': settings.sslmode
    }


