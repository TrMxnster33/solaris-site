import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


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
SESSION_SECONDS = 24 * 60 * 60
REMEMBER_SESSION_SECONDS = 30 * 24 * 60 * 60
ADMIN_PAGE_SIZE = 50
ANALYTICS_RETENTION_DAYS = int(os.environ.get("ANALYTICS_RETENTION_DAYS", "90"))
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,16}\Z")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\Z")


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
        salt = bytes.fromhex(salt_hex)
        digest = bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(digest) != 32:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, 310_000)
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


def valid_legacy_hash(stored):
    if not isinstance(stored, str):
        return False
    try:
        salt, digest = stored.split(":", 1)
        return len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 32
    except (ValueError, TypeError):
        return False


def trusted_proxy_networks():
    return [
        ipaddress.ip_network(value.strip(), strict=False)
        for value in os.environ.get("TRUSTED_PROXIES", "").split(",")
        if value.strip()
    ]


def create_users_table(connection, table="users"):
    connection.execute(
        f"""CREATE TABLE {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
            created_at INTEGER NOT NULL
        )"""
    )


def migrate_users(connection):
    existing = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not existing:
        create_users_table(connection)
        return False

    columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    if {"id", "email", "username", "password_hash", "role", "created_at"}.issubset(columns):
        return False

    connection.execute("DROP TABLE IF EXISTS users_new")
    create_users_table(connection, "users_new")
    if {"id", "email", "name", "password_hash", "role", "created_at"}.issubset(columns):
        legacy_users = connection.execute(
            "SELECT id, email, name, password_hash, role, created_at FROM users"
        ).fetchall()
        for user in legacy_users:
            email = (user["email"] or "").strip().lower()
            username = (user["name"] or "").strip()
            if (
                not EMAIL_PATTERN.fullmatch(email)
                or email.endswith("@minecraft.local")
                or not USERNAME_PATTERN.fullmatch(username)
                or not valid_legacy_hash(user["password_hash"])
            ):
                continue
            try:
                connection.execute(
                    """INSERT INTO users_new
                       (id, email, username, password_hash, role, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        user["id"], email, username, user["password_hash"],
                        user["role"] if user["role"] in ("user", "admin") else "user",
                        user["created_at"],
                    ),
                )
            except sqlite3.IntegrityError:
                continue

    connection.execute("DROP TABLE IF EXISTS sessions")
    connection.execute("DROP TABLE users")
    connection.execute("ALTER TABLE users_new RENAME TO users")
    return True


def initialize():
    if ANALYTICS_RETENTION_DAYS < 1:
        raise ValueError("ANALYTICS_RETENTION_DAYS en az 1 olmalı.")
    trusted_proxy_networks()
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        migrate_users(connection)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS analytics_visitors (
                visitor_hash TEXT PRIMARY KEY,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                ip_address TEXT NOT NULL,
                device_type TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_hash TEXT NOT NULL,
                page TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device_type TEXT NOT NULL,
                referrer TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                visited_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS page_views_visited_at_idx ON page_views(visited_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS page_views_visitor_hash_idx ON page_views(visitor_hash)"
        )

        admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            if not EMAIL_PATTERN.fullmatch(admin_email) or len(admin_password) < 10:
                raise ValueError("ADMIN_EMAIL geçerli olmalı; ADMIN_PASSWORD en az 10 karakter olmalı.")
            admin = connection.execute(
                "SELECT id FROM users WHERE email = ?", (admin_email,)
            ).fetchone()
            password_hash = hash_secret(admin_password)
            admin_username = os.environ.get("ADMIN_USERNAME", "babakutletenv4").strip()
            if not USERNAME_PATTERN.fullmatch(admin_username):
                raise ValueError("ADMIN_USERNAME 3-16 karakter, harf/rakam/alt çizgi olmalı.")
            username_owner = connection.execute(
                "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                (admin_username,),
            ).fetchone()
            if username_owner and (not admin or username_owner["id"] != admin["id"]):
                raise ValueError("ADMIN_USERNAME başka bir hesap tarafından kullanılıyor.")
            if admin:
                connection.execute(
                    "UPDATE users SET username=?, role='admin', password_hash=? WHERE id=?",
                    (admin_username, password_hash, admin["id"]),
                )
            else:
                connection.execute(
                    """INSERT INTO users (email, username, password_hash, role, created_at)
                       VALUES (?, ?, ?, 'admin', ?)""",
                    (admin_email, admin_username, password_hash, int(time.time())),
                )

        now = int(time.time())
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        cutoff = now - ANALYTICS_RETENTION_DAYS * 24 * 60 * 60
        connection.execute("DELETE FROM page_views WHERE visited_at < ?", (cutoff,))
        connection.execute("DELETE FROM analytics_visitors WHERE last_seen < ?", (cutoff,))


class Handler(BaseHTTPRequestHandler):
    server_version = "Solaris/2.0"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (
            self.address_string(), self.log_date_time_string(), fmt % args
        ))

    def security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
        )

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.security_headers()
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
        return connection.execute(
            """SELECT users.* FROM sessions
               JOIN users ON users.id = sessions.user_id
               WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
            (token_hash, int(time.time())),
        ).fetchone()

    @staticmethod
    def public_user(user):
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "created_at": user["created_at"],
        }

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/"):
            self.handle_api_get(path)
            return
        if path in ("/", "/admin", "/admin/"):
            path = "/index.html"
        requested = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC.resolve() not in requested.parents or not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }
        body = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            content_types.get(requested.suffix, "application/octet-stream"),
        )
        self.send_header("Content-Length", str(len(body)))
        self.security_headers()
        self.end_headers()
        self.wfile.write(body)

    def handle_api_get(self, path):
        parsed_request = urlparse(self.path)
        query = parse_qs(parsed_request.query)
        with db() as connection:
            user = self.current_user(connection)
            if path == "/api/me":
                self.send_json(
                    HTTPStatus.OK,
                    {"user": self.public_user(user) if user else None},
                )
                return
            if path == "/api/site-config":
                self.send_json(HTTPStatus.OK, {
                    "minecraft_address": os.environ.get("MINECRAFT_ADDRESS", "").strip(),
                    "minecraft_version": os.environ.get("MINECRAFT_VERSION", "Java").strip(),
                })
                return
            if path == "/api/admin/analytics":
                if not user or user["role"] != "admin":
                    self.send_json(HTTPStatus.FORBIDDEN, {"error": "Yönetici yetkisi gerekli."})
                    return
                now = int(time.time())
                try:
                    visits_page = max(1, int(query.get("visits_page", ["1"])[0]))
                    users_page = max(1, int(query.get("users_page", ["1"])[0]))
                except ValueError:
                    self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Geçersiz panel sayfası."})
                    return
                metrics = {
                    "online": connection.execute(
                        "SELECT COUNT(*) FROM analytics_visitors WHERE last_seen >= ?",
                        (now - 300,),
                    ).fetchone()[0],
                    "visitors": connection.execute(
                        "SELECT COUNT(*) FROM analytics_visitors"
                    ).fetchone()[0],
                    "page_views": connection.execute(
                        "SELECT COUNT(*) FROM page_views"
                    ).fetchone()[0],
                }
                metrics["users"] = connection.execute(
                    "SELECT COUNT(*) FROM users"
                ).fetchone()[0]
                metrics["recorded_visits"] = metrics["page_views"]
                visit_count = metrics["page_views"]
                user_count = metrics["users"]
                visit_pages = max(1, (visit_count + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
                user_pages = max(1, (user_count + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
                visits_page = min(visits_page, visit_pages)
                users_page = min(users_page, user_pages)
                visits = connection.execute(
                    """SELECT page, ip_address, device_type, referrer, user_agent,
                              language, visited_at
                       FROM page_views ORDER BY visited_at DESC, id DESC
                       LIMIT ? OFFSET ?""",
                    (ADMIN_PAGE_SIZE, (visits_page - 1) * ADMIN_PAGE_SIZE),
                ).fetchall()
                users = connection.execute(
                    """SELECT id, username, email, role, created_at
                       FROM users ORDER BY created_at DESC, id DESC
                       LIMIT ? OFFSET ?""",
                    (ADMIN_PAGE_SIZE, (users_page - 1) * ADMIN_PAGE_SIZE),
                ).fetchall()
                self.send_json(HTTPStatus.OK, {
                    "metrics": metrics,
                    "visits": [dict(row) for row in visits],
                    "users": [dict(row) for row in users],
                    "pagination": {
                        "page_size": ADMIN_PAGE_SIZE,
                        "visits_page": visits_page,
                        "visits_pages": visit_pages,
                        "visits_total": visit_count,
                        "users_page": users_page,
                        "users_pages": user_pages,
                        "users_total": user_count,
                    },
                })
                return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "İstenen API bulunamadı."})

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
            self.send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "İşlem tamamlanamadı. Lütfen daha sonra tekrar deneyin."},
            )

    def register(self, data):
        email = data.get("email")
        username = data.get("username")
        password = data.get("password")
        password_confirm = data.get("password_confirm")
        if not isinstance(email, str) or not EMAIL_PATTERN.fullmatch(email.strip()):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Geçerli bir e-posta adresi girin."})
            return
        email = email.strip().lower()
        if len(email) > 254:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "E-posta adresi çok uzun."})
            return
        if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username.strip()):
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Oyuncu adı 3-16 karakter olmalı; yalnızca harf, rakam ve alt çizgi kullanın."},
            )
            return
        username = username.strip()
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Parola en az 10, en fazla 128 karakter olmalı."},
            )
            return
        if password != password_confirm:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Parolalar eşleşmiyor."})
            return
        now = int(time.time())
        try:
            with db() as connection:
                cursor = connection.execute(
                    """INSERT INTO users (email, username, password_hash, role, created_at)
                       VALUES (?, ?, ?, 'user', ?)""",
                    (email, username, hash_secret(password), now),
                )
                user = connection.execute(
                    "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                cookie = self.create_session(connection, user["id"], remember=False)
        except sqlite3.IntegrityError:
            self.send_json(
                HTTPStatus.CONFLICT,
                {"error": "Bu e-posta adresi veya oyuncu adı zaten kullanılıyor."},
            )
            return
        self.send_json(
            HTTPStatus.CREATED,
            {"user": self.public_user(user)},
            {"Set-Cookie": cookie},
        )

    def create_session(self, connection, user_id, remember):
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        lifetime = REMEMBER_SESSION_SECONDS if remember else SESSION_SECONDS
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, int(time.time()) + lifetime),
        )
        secure = "; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else ""
        max_age = f"; Max-Age={lifetime}" if remember else ""
        return f"solaris_session={token}; Path=/; HttpOnly; SameSite=Lax{max_age}{secure}"

    def login(self, data):
        identity = data.get("email_or_username")
        password = data.get("password")
        if not isinstance(identity, str) or not identity.strip() or not isinstance(password, str):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "E-posta/oyuncu adı ve parola gerekli."})
            return
        identity = identity.strip()
        with db() as connection:
            user = connection.execute(
                """SELECT * FROM users
                   WHERE email = ? COLLATE NOCASE OR username = ? COLLATE NOCASE""",
                (identity.lower(), identity),
            ).fetchone()
            if not user or not verify_secret(password, user["password_hash"]):
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Giriş bilgileri hatalı."})
                return
            cookie = self.create_session(
                connection, user["id"], remember=data.get("remember_me") is True
            )
        self.send_json(
            HTTPStatus.OK,
            {"user": self.public_user(user)},
            {"Set-Cookie": cookie},
        )

    def logout(self, _data):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_session")
        if morsel:
            token_hash = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
            with db() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        secure = "; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else ""
        self.send_json(
            HTTPStatus.OK,
            {"message": "Oturum kapatıldı."},
            {"Set-Cookie": f"solaris_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure}"},
        )

    def analytics_consent(self, data):
        if data.get("consent") is not True:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Analitik için açık kullanıcı onayı gereklidir."},
            )
            return False
        return True

    def visitor_identity(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_visitor")
        token = morsel.value if morsel else secrets.token_urlsafe(32)
        visitor_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cookie_header = None
        if not morsel:
            secure = "; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else ""
            cookie_header = (
                f"solaris_visitor={token}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age=31536000{secure}"
            )
        return visitor_hash, cookie_header

    def client_ip_address(self):
        address = self.client_address[0]
        peer = ipaddress.ip_address(address)
        trusted = trusted_proxy_networks()
        if any(peer in network for network in trusted):
            chain = []
            for value in self.headers.get("X-Forwarded-For", "").split(","):
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
        if any(value in user_agent for value in ("ipad", "tablet")):
            return "Tablet"
        if any(value in user_agent for value in ("mobile", "android", "iphone", "ipod")):
            return "Mobil"
        return "Masaüstü"

    def track_visit(self, data):
        if not self.analytics_consent(data):
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
        try:
            source_url = urlparse(source[:2048] if isinstance(source, str) else "")
            referrer = source_url.hostname if source_url.scheme in ("http", "https") else ""
            if not referrer:
                referrer = urlparse(self.headers.get("Referer", "")).hostname or ""
        except ValueError:
            referrer = ""
        with db() as connection:
            connection.execute(
                """INSERT INTO analytics_visitors
                   (visitor_hash, first_seen, last_seen, ip_address, device_type)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(visitor_hash) DO UPDATE SET last_seen=excluded.last_seen,
                   ip_address=excluded.ip_address, device_type=excluded.device_type""",
                (visitor_hash, now, now, address, device),
            )
            connection.execute(
                """INSERT INTO page_views
                   (visitor_hash, page, ip_address, device_type, referrer, user_agent, language, visited_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    visitor_hash,
                    (parsed_page.path or "/") + (f"#{parsed_page.fragment}" if parsed_page.fragment else ""),
                    address,
                    device,
                    referrer or "",
                    self.headers.get("User-Agent", "")[:500],
                    self.headers.get("Accept-Language", "")[:100],
                    now,
                ),
            )
            cutoff = now - ANALYTICS_RETENTION_DAYS * 24 * 60 * 60
            connection.execute("DELETE FROM page_views WHERE visited_at < ?", (cutoff,))
            connection.execute("DELETE FROM analytics_visitors WHERE last_seen < ?", (cutoff,))
        headers = {"Set-Cookie": cookie_header} if cookie_header else None
        self.send_json(HTTPStatus.OK, {"tracked": True}, headers)

    def track_heartbeat(self, data):
        if not self.analytics_consent(data):
            return
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("solaris_visitor")
        if not morsel:
            self.send_json(HTTPStatus.OK, {"tracked": False})
            return
        visitor_hash = hashlib.sha256(morsel.value.encode("utf-8")).hexdigest()
        with db() as connection:
            connection.execute(
                "UPDATE analytics_visitors SET last_seen=? WHERE visitor_hash=?",
                (int(time.time()), visitor_hash),
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
        secure = "; Secure" if os.environ.get("COOKIE_SECURE", "false").lower() == "true" else ""
        self.send_json(
            HTTPStatus.OK,
            {"message": "Analitik tercihiniz güncellendi."},
            {"Set-Cookie": f"solaris_visitor=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure}"},
        )


def main():
    initialize()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Solaris web hesabı sunucusu http://{HOST}:{PORT} adresinde çalışıyor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSolaris sunucusu kapatılıyor.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
