# JOD_VPN — сервер с базой данных PostgreSQL (Aiven)
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from urllib.parse import urlparse, parse_qs
import psycopg2
import psycopg2.extras

# === НАСТРОЙКИ БАЗЫ ДАННЫХ ===
DB_HOST = "pg-ebc96d1-jodvpn-roulette.d.aivencloud.com"
DB_PORT = 17848
DB_USER = "avnadmin"
DB_PASSWORD = "AVNS_jV4O-TKLgyOI0ICcZvg"
DB_NAME = "defaultdb"

# === ПОДКЛЮЧЕНИЕ К БАЗЕ ===
def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require"
    )

def init_db():
    """Создаёт таблицы, если их нет"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    login TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    login TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)
            # Создаём админа по умолчанию, если его нет
            cur.execute("SELECT COUNT(*) FROM admin")
            count = cur.fetchone()[0]
            if count == 0:
                default_admin = {"login": "admin", "key": "jodvpn2026"}
                cur.execute(
                    "INSERT INTO admin (login, data) VALUES (%s, %s)",
                    (default_admin["login"], json.dumps(default_admin, ensure_ascii=False))
                )
        conn.commit()

# === РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ===
def load_users():
    users = {}
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT data FROM users")
            for row in cur.fetchall():
                u = row["data"]
                users[u["login"]] = u
    return users

def save_user(user):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (login, data) VALUES (%s, %s) "
                "ON CONFLICT (login) DO UPDATE SET data = EXCLUDED.data",
                (user["login"], json.dumps(user, ensure_ascii=False))
            )
        conn.commit()

def delete_user(login):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE login = %s", (login,))
        conn.commit()

# === РАБОТА С АДМИНОМ ===
def load_admin():
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT data FROM admin LIMIT 1")
            row = cur.fetchone()
            if row:
                return row["data"]
    return {"login": "admin", "key": "jodvpn2026"}

# === HTTP ОБРАБОТЧИК ===
class Handler(BaseHTTPRequestHandler):
    def _set_headers(self, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # Проверка работоспособности
        if path == "/" or path == "":
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok",
                "server": "JOD_VPN",
                "database": "PostgreSQL"
            }).encode('utf-8'))
            return

        # GET /users
        if path == "/users":
            self._set_headers(200)
            self.wfile.write(json.dumps(load_users(), ensure_ascii=False).encode('utf-8'))
            return

        # GET /user?login=xxx
        if path == "/user":
            login = params.get("login", [None])[0]
            if not login:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "no login"}).encode('utf-8'))
                return
            users = load_users()
            if login in users:
                self._set_headers(200)
                self.wfile.write(json.dumps(users[login], ensure_ascii=False).encode('utf-8'))
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "not found"}).encode('utf-8'))
            return

        # GET /auth?login=xxx&key=yyy
        if path == "/auth":
            login = params.get("login", [None])[0]
            key = params.get("key", [None])[0]
            if not login or not key:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "no login/key"}).encode('utf-8'))
                return

            admin = load_admin()
            if login == admin["login"] and key == admin["key"]:
                self._set_headers(200)
                self.wfile.write(json.dumps({"ok": True, "role": "admin"}).encode('utf-8'))
                return

            users = load_users()
            if login in users and users[login].get("key") == key:
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "ok": True,
                    "role": "user",
                    "user": users[login]
                }, ensure_ascii=False).encode('utf-8'))
                return

            self._set_headers(401)
            self.wfile.write(json.dumps({"ok": False, "error": "invalid"}).encode('utf-8'))
            return

        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "not found"}).encode('utf-8'))

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else "{}"
        try:
            data = json.loads(body)
        except:
            data = {}

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/user":
            login = data.get("login")
            if not login:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "no login"}).encode('utf-8'))
                return
            save_user(data)
            self._set_headers(200)
            self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))
            return

        if path == "/delete":
            login = data.get("login")
            delete_user(login)
            self._set_headers(200)
            self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))
            return

        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "not found"}).encode('utf-8'))

    def log_message(self, format, *args):
        pass

# === ЗАПУСК ===
def run():
    print("=" * 50)
    print("JOD_VPN — СЕРВЕР С POSTGRESQL")
    print("=" * 50)
    try:
        init_db()
        print("✅ База данных подключена и инициализирована")
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")

    port = int(os.environ.get("PORT", 7860))
    print(f"🚀 Сервер запущен на порту {port}")
    print("=" * 50)

    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

if __name__ == "__main__":
    run()