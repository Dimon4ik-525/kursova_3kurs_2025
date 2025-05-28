import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

# 🗄 Параметри підключення до бази даних PostgreSQL
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")