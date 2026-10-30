import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    import mysql.connector
except ImportError:
    mysql.connector = None


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"

def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env()
DATABASE = Path(os.environ.get("SOLARIS_DB", ROOT / "solaris.db"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
SESSION_SECONDS = 7 * 24 * 60 * 60
ANALYTICS_RETENTION_DAYS = int(os.environ.get("ANALYTICS_RETENTION_DAYS", "90"))

# Clever Cloud MySQL (AuthMe) Bağlantı Bilgileri
MYSQL_HOST = os.environ.get("MYSQL_HOST", "bky6svowc5ii6zdpz6re-mysql.services.clever-cloud.com")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "bky6svowc5ii6zdpz6re")
MYSQL_USER = os.environ.get("MYSQL_USER", "uriunt57hec5j0xr")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "ejbChDBwRr0bwRZ9dE1S")


def mysql_db():
    if mysql.connector is None:
        raise RuntimeError("mysql-connector-python kütüphanesi yüklü değil.")
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        database=MYSQL_DATABASE,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        ssl_disabled=False,
        ssl_verify_cert=False,
        timeout=15
    )


def db():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_secret(value, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, 310_000)
    return salt.hex() + ":" + digest.hex()


def verify_secret(value, stored):
    if not isinstance(value, str) or not isinstance(stored, str):
        return False
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        candidate = hash_secret(value, bytes.fromhex(salt_hex)).split(":", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError, AttributeError):
        return False


def trusted_proxy_networks():
    return [
        ipaddress.ip_network(value.strip(), strict=False)
        for value in os.environ.get("TRUSTED_PROXIES", "").split(",")
        if value.strip()
    ]


def initialize():
    if ANALYTICS_RETENTION_DAYS < 1:
        raise ValueError("ANALYTICS_RETENTION_DAYS en az 1 olmalı.")
    trusted_proxy_networks()
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                verified INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                verification_hash TEXT,
                verification_expires INTEGER,
                verification_sent INTEGER,
                verification_attempts INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analytics_visitors (
                visitor_hash TEXT PRIMARY KEY,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                ip_address TEXT NOT NULL,
                device_type TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_hash TEXT NOT NULL,
                page TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device_type TEXT NOT NULL,
                referrer TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                visited_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS page_views_visited_at_idx ON page_views(visited_at);
            CREATE INDEX IF NOT EXISTS page_views_visitor_hash_idx ON page_views(visitor_hash);
            """
        )
        admin_email = os.environ.get("ADMIN_EMAIL", "eymenefeyt3@gmail.com").strip().lower()
        admin = connection.execute(
            "SELECT id FROM users WHERE email=? AND role='admin'", (admin_email,)
        ).fetchone()
        if not admin:
            admin_password = os.environ.get("ADMIN_PASSWORD", "SolarisAdmin2026!")
            admin_name = os.environ.get("ADMIN_NAME", "Solaris Admin")
            connection.execute(
                """INSERT INTO users
                    (name, email, password_hash, role, verified, must_change_password, created_at)
                    VALUES (?, ?, ?, 'admin', 1, 0, ?)""",
                (admin_name, admin_email, hash_secret(admin_password), int(time.time())),
            )
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        if ANALYTICS_RETENTION_DAYS > 0:
            cutoff = int(time.time()) - ANALYTICS_RETENTION_DAYS * 24 * 60 * 60
            connection.execute("DELETE FROM page_views WHERE visited_at < ?", (cutoff,))
            connection.execute("DELETE FROM analytics_visitors WHERE last_seen < ?", (cutoff,))


class Handler(BaseHTTPRequestHandler):
    server_version = "Solaris/1.0"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        if headers:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("İstek JSON biçiminde olmalı.")
        length = int(self.headers.get("Content-Length", "0"))
        if length > 16_384:
            raise ValueError("İstek çok büyük.")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("Geçersiz istek.")
        return data

    def request_origin_is_local(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.netloc.lower() == self.headers.get("Host", "").lower()

    def current_user(self, connection):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_session")
        if not morsel:
            return None
        token_hash = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
        row = connection.execute(
            """SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id
               WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
            (token_hash, int(time.time())),
        ).fetchone()
        return row

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/"):
            self.handle_api_get(path)
            return
        if path in ("/admin", "/admin/"):
            path = "/index.html"
        if path == "/":
            path = "/index.html"
        requested = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC.resolve() not in requested.parents or not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8"
        if requested.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif requested.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif requested.suffix == ".svg":
            content_type = "image/svg+xml"
        body = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)

    def handle_api_get(self, path):
        with db() as connection:
            user = self.current_user(connection)
            if path == "/api/me":
                if user is None:
                    self.send_json(HTTPStatus.OK, {"user": None})
                else:
                    self.send_json(HTTPStatus.OK, {"user": self.public_user(user)})
                return
            if path == "/api/site-config":
                self.send_json(HTTPStatus.OK, {
                    "minecraft_address": os.environ.get("MINECRAFT_ADDRESS", "").strip(),
                    "minecraft_version": os.environ.get("MINECRAFT_VERSION", "Java").strip(),
                })
                return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "İstenen API bulunamadı."})

    @staticmethod
    def public_user(user):
        return {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "must_change_password": bool(user["must_change_password"]),
        }

    def do_POST(self):
        if not self.request_origin_is_local():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Geçersiz istek kaynağı."})
            return
        try:
            data = self.body_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        path = urlparse(self.path).path
        actions = {
            "/api/register": self.register,
            "/api/login": self.login,
            "/api/logout": self.logout,
            "/api/change-password": self.change_password,
            "/api/track": self.track_visit,
            "/api/heartbeat": self.track_heartbeat,
            "/api/revoke-analytics": self.revoke_analytics,
        }
        action = actions.get(path)
        if action is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "İstenen API bulunamadı."})
            return
        try:
            action(data)
        except (sqlite3.Error, OSError) as error:
            print(f"İstek hatası: {error}")
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "İşlem tamamlanamadı. Lütfen daha sonra tekrar deneyin."})

    def register(self, data):
        username = data.get("username")
        password = data.get("password", "")
        password_confirm = data.get("password_confirm", "")

        if not isinstance(username, str) or not username.strip():
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Kullanıcı adı gerekli."})
            return
        username = username.strip()

        if len(username) > 16 or not re.fullmatch(r"[a-zA-Z0-9_]+", username):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Geçersiz kullanıcı adı (en fazla 16 karakter, harf, rakam ve alt çizgi olmalı)."})
            return

        if not password or len(password) < 4:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Parola en az 4 karakter olmalı."})
            return

        if password != password_confirm:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Parolalar birbiriyle eşleşmiyor."})
            return

        try:
            conn = mysql_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM authme WHERE username = %s", (username,))
            existing = cursor.fetchone()
            if existing:
                cursor.close()
                conn.close()
                self.send_json(HTTPStatus.CONFLICT, {"error": "Bu kullanıcı adı zaten kayıtlı."})
                return

            # AuthMe SHA-256 şifreleme
            password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            now_ms = int(time.time() * 1000)

            cursor.execute(
                "INSERT INTO authme (username, realname, password, ip, lastlogin, regdate, regip) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (username, username, password_hash, "127.0.0.1", 0, now_ms, "127.0.0.1")
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as error:
            print(f"MySQL kayıt hatası: {error}")
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Oyun veritabanına bağlanılamadı. Lütfen daha sonra tekrar deneyin."})
            return

        self.send_json(HTTPStatus.OK, {"message": "Kayıt başarılı! Şimdi giriş yapabilirsiniz."})

    def login(self, data):
        username = data.get("username")
        password = data.get("password", "")

        if not isinstance(username, str) or not username.strip():
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Kullanıcı adı ve parola gerekli."})
            return
        username = username.strip()

        try:
            conn = mysql_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM authme WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
        except Exception as error:
            print(f"MySQL bağlantı hatası: {error}")
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Oyun veritabanına şu anda bağlanılamıyor."})
            return

        if not user_data:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Kullanıcı adı veya parola hatalı."})
            return

        db_password_hash = user_data["password"]
        input_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

        if not hmac.compare_digest(input_hash, db_password_hash):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Kullanıcı adı veya parola hatalı."})
            return

        mc_email = f"{username.lower()}@minecraft.local"
        with db() as connection:
            user = connection.execute("SELECT * FROM users WHERE email = ?", (mc_email,)).fetchone()
            if not user:
                now = int(time.time())
                connection.execute(
                    """INSERT INTO users (name, email, password_hash, role, verified, must_change_password, created_at)
                       VALUES (?, ?, ?, 'user', 1, 0, ?)""",
                    (username, mc_email, db_password_hash, now)
                )
                user = connection.execute("SELECT * FROM users WHERE email = ?", (mc_email,)).fetchone()

            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            expires = int(time.time()) + SESSION_SECONDS
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user["id"], expires),
            )

        secure = "; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else ""
        cookie = f"solaris_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_SECONDS}{secure}"
        self.send_json(HTTPStatus.OK, {"user": self.public_user(user)}, {"Set-Cookie": cookie})

    def logout(self, _data):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_session")
        if morsel:
            token_hash = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
            with db() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        self.send_json(
            HTTPStatus.OK,
            {"message": "Oturum kapatıldı."},
            {"Set-Cookie": "solaris_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"},
        )

    def analytics_consent(self, data):
        if data.get("consent") is not True:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Analitik için açık kullanıcı onayı gereklidir."})
            return None
        return True

    def visitor_identity(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_visitor")
        token = morsel.value if morsel else secrets.token_urlsafe(32)
        visitor_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cookie_header = None
        if not morsel:
            secure = "; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else ""
            cookie_header = f"solaris_visitor={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000{secure}"
        return visitor_hash, cookie_header

    def client_ip_address(self):
        address = self.client_address[0]
        trusted = trusted_proxy_networks()
        peer = ipaddress.ip_address(address)
        if any(peer in network for network in trusted):
            forwarded = self.headers.get("X-Forwarded-For", "").split(",")
            chain = []
            for value in forwarded:
                try:
                    chain.append(ipaddress.ip_address(value.strip()))
                except ValueError:
                    continue
            for candidate in reversed(chain):
                if not any(candidate in network for network in trusted):
                    return str(candidate)
        return address

    def device_type(self):
        user_agent = self.headers.get("User-Agent", "").lower()
        if any(device in user_agent for device in ("mobile", "android", "iphone", "ipod")):
            return "Mobil"
        if any(device in user_agent for device in ("tablet", "ipad")):
            return "Tablet"
        return "Masaüstü"

    def track_visit(self, data):
        self.analytics_consent(data)
        if data.get("consent") is not True:
            return
        page = data.get("page")
        if not isinstance(page, str) or not page.startswith("/") or page.startswith("//") or len(page) > 500:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Geçerli bir sayfa yolu gerekli."})
            return
        parsed_page = urlparse(page)
        if parsed_page.scheme or parsed_page.netloc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Yalnızca site içi sayfalar kaydedilebilir."})
            return
        visitor_hash, cookie_header = self.visitor_identity()
        now = int(time.time())
        address = self.client_ip_address()
        device = self.device_type()
        source = data.get("source", "")
        referrer = ""
        try:
            source_url = urlparse(source[:2048] if isinstance(source, str) else "")
            if source_url.scheme in ("http", "https"):
                referrer = source_url.hostname or ""
            if not referrer:
                referrer_url = urlparse(self.headers.get("Referer", ""))
                referrer = referrer_url.hostname or ""
        except ValueError:
            referrer = ""
        user_agent = self.headers.get("User-Agent", "")[:500]
        language = self.headers.get("Accept-Language", "")[:100]
        with db() as connection:
            connection.execute(
                """INSERT INTO analytics_visitors (visitor_hash, first_seen, last_seen, ip_address, device_type)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(visitor_hash) DO UPDATE SET last_seen=excluded.last_seen,
                   ip_address=excluded.ip_address, device_type=excluded.device_type""",
                (visitor_hash, now, now, address, device),
            )
            connection.execute(
                """INSERT INTO page_views
                   (visitor_hash, page, ip_address, device_type, referrer, user_agent, language, visited_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (visitor_hash, (parsed_page.path or "/") + (f"#{parsed_page.fragment}" if parsed_page.fragment else ""),
                 address, device, referrer, user_agent, language, now),
            )
            if ANALYTICS_RETENTION_DAYS > 0:
                cutoff = now - ANALYTICS_RETENTION_DAYS * 24 * 60 * 60
                connection.execute("DELETE FROM page_views WHERE visited_at < ?", (cutoff,))
                connection.execute("DELETE FROM analytics_visitors WHERE last_seen < ?", (cutoff,))
        headers = {"Set-Cookie": cookie_header} if cookie_header else None
        self.send_json(HTTPStatus.OK, {"tracked": True}, headers)

    def track_heartbeat(self, data):
        if data.get("consent") is not True:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Analitik için açık kullanıcı onayı gereklidir."})
            return
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_visitor")
        if not morsel:
            self.send_json(HTTPStatus.OK, {"tracked": False})
            return
        visitor_hash = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
        now = int(time.time())
        with db() as connection:
            connection.execute(
                "UPDATE analytics_visitors SET last_seen=? WHERE visitor_hash=?",
                (now, visitor_hash),
            )
        self.send_json(HTTPStatus.OK, {"tracked": True})

    def revoke_analytics(self, _data):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_visitor")
        if morsel:
            visitor_hash = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
            with db() as connection:
                connection.execute("DELETE FROM page_views WHERE visitor_hash=?", (visitor_hash,))
                connection.execute("DELETE FROM analytics_visitors WHERE visitor_hash=?", (visitor_hash,))
        self.send_json(
            HTTPStatus.OK,
            {"message": "Analitik tercihiniz güncellendi."},
            {"Set-Cookie": "solaris_visitor=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" +
             ("; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else "")},
        )

    def change_password(self, data):
        old_password = data.get("old_password", "")
        new_password = data.get("new_password", "")
        if not isinstance(new_password, str) or len(new_password) < 4:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Yeni parola en az 4 karakter olmalı."})
            return
        with db() as connection:
            user = self.current_user(connection)
            if not user:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Önce giriş yapmalısınız."})
                return
            connection.execute(
                "UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
                (hash_secret(new_password), user["id"]),
            )
        self.send_json(HTTPStatus.OK, {"message": "Parolanız güncellendi. Lütfen tekrar giriş yapın."})


def main():
    initialize()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Solaris çalışıyor: http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSolaris kapatılıyor.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
