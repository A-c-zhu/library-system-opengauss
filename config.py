import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', '数据库名')
    DB_USER = os.getenv('DB_USER', '用户名')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '密码')