from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FK_ID = os.getenv("FK_ID")
FK_SECRET1 = os.getenv("FK_SECRET1")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
