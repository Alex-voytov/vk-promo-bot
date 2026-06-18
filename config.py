import os
from dotenv import load_dotenv

load_dotenv()

VK_TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", 0))
MAIN_ADMIN_ID = int(os.getenv("MAIN_ADMIN_ID", 0))
PROMO_FILE = os.getenv("PROMO_FILE", "promocodes.txt")
DB_FILE = os.getenv("DB_FILE", "database.db")
