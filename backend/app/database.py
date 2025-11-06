"""資料庫連線管理 - 重用現有 db_config.py 的邏輯"""
import psycopg
from contextlib import contextmanager
from app.config import get_db_config

def get_connection():
    """建立資料庫連線"""
    try:
        config = get_db_config()
        return psycopg.connect(**config)
    except Exception as e:
        raise RuntimeError(f"資料庫連線失敗：{e}")

@contextmanager
def get_cursor():
    """取得資料庫游標（自動處理連線與游標關閉）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


