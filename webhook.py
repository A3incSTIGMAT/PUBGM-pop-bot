# webhook.py — Обработчик платежей Free-Kassa
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import hashlib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Подключаем настройки
try:
    from config import MERCHANT_ID, SECRET_1, SECRET_2
except ImportError:
    logger.error("❌ Не найден config.py — используй config.example.py как образец")
    exit()

class FreeKassaHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = urllib.parse.parse_qs(post_data)

        try:
            order_id = data.get('MERCHANT_ORDER_ID', [''])[0]
            amount = data.get('AMOUNT', [''])[0]
            sign = data.get('SIGN', [''])[0]

            sign_check = hashlib.md5(f"{MERCHANT_ID}:{amount}:{SECRET_1}:{order_id}".encode()).hexdigest()
            if sign.lower() != sign_check.lower():
                logger.warning("❌ Неверная подпись")
                self.send_response(400)
                self.end_headers()
                return

            if "_" in order_id:
                user_id_str, item = order_id.split("_", 1)
                try:
                    user_id = int(user_id_str)
                    points_map = {
                        "chicken": 10,
                        "motorcycle": 200,
                        "gold": 800,
                        "car": 2000,
                        "money_gun": 3000,
                        "kiss": 4000
                    }
                    points = points_map.get(item, 0)
                    if points > 0:
                        conn = sqlite3.connect("users.db")
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET popular_points = popular_points + ? WHERE user_id = ?",
                            (points, user_id)
                        )
                        conn.commit()
                        conn.close()
                        logger.info(f"✅ Платёж подтверждён: user_id={user_id}, +{points} очков")
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки: {e}")

            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"YES")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            self.send_response(500)
            self.end_headers()

if __name__ == "__main__":
    from config import MERCHANT_ID, SECRET_1, SECRET_2
    server = HTTPServer(('0.0.0.0', 8000), FreeKassaHandler)
    logger.info("🚀 Вебхук запущен на порту 8000")
    server.serve_forever()
