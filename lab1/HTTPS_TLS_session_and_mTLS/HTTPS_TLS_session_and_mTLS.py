
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import json
import secrets
import threading
from pathlib import Path
from http.cookies import SimpleCookie

sessions = {}


class CMyHandler(BaseHTTPRequestHandler):
    def do_GET(self):

        if self.path == "/":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"HTTPS server working!")

        elif self.path == "/me":
            cookies = SimpleCookie()
            try:
                cookies.load(
                    self.headers.get("Cookie", "")
                )

                session_cookie = cookies.get("session")

                token = (
                    session_cookie.value
                    if session_cookie else None
                )

            except Exception:
                token = None

            if token and token in sessions:
                username = sessions[token]

                response = json.dumps({
                    "user": username
                }).encode("utf-8")

                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json"
                )
                self.send_header(
                    "Content-Length", str(len(response))
                )
                self.end_headers()
                self.wfile.write(response)

            else:
                self.send_error(401)

        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/login":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8192:
                self.send_error(400)
                return

            body = self.rfile.read(length)
            data = json.loads(body)

            username = data["user"]
            password = data["password"]

        except (ValueError, KeyError, TypeError):
            self.send_error(400)
            return

        if not isinstance(username, str) or not username or password != "netsec":
            self.send_error(401)
            return

        token = secrets.token_urlsafe(32)
        sessions[token] = username

        self.send_response(200)
        self.send_header(
            "Set-Cookie",
            f"session={token}; Path=/; Secure; HttpOnly; SameSite=Lax"
        )
        self.send_header("Content-Length", "0")
        self.end_headers()


class CMTLSHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/whoami":
            self.send_error(404)
            return

        cert = self.connection.getpeercert()

        if not cert:
            self.send_error(401)
            return

        common_name = None

        for rdn in cert.get("subject", ()):
            for key, value in rdn:
                if key == "commonName":
                    common_name = value
                    break

            if common_name is not None:
                break

        if common_name is None:
            self.send_error(403)
            return

        body = common_name.encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type", "text/plain; charset=utf-8"
        )
        self.send_header(
            "Content-Length", str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)


BASE_DIR = Path(__file__).resolve().parent

https_server = HTTPServer(
    ("0.0.0.0", 8443),
    CMyHandler
)

https_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
https_context.minimum_version = ssl.TLSVersion.TLSv1_2

https_context.load_cert_chain(
    certfile=str(BASE_DIR / "server.crt"),
    keyfile=str(BASE_DIR / "server.key")
)

https_server.socket = https_context.wrap_socket(
    https_server.socket,
    server_side=True
)


mtls_server = HTTPServer(
    ("0.0.0.0", 8444),
    CMTLSHandler
)

mtls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
mtls_context.minimum_version = ssl.TLSVersion.TLSv1_2

mtls_context.load_cert_chain(
    certfile=str(BASE_DIR / "server.crt"),
    keyfile=str(BASE_DIR / "server.key")
)

mtls_context.load_verify_locations(
    cafile=str(BASE_DIR / "ca.crt")
)

mtls_context.verify_mode = ssl.CERT_REQUIRED

mtls_server.socket = mtls_context.wrap_socket(
    mtls_server.socket,
    server_side=True
)


https_thread = threading.Thread(
    target=https_server.serve_forever,
    daemon=True
)

https_thread.start()

print("HTTPS server running on port 8443", flush=True)
print("mTLS server running on port 8444", flush=True)

try:
    mtls_server.serve_forever()
except KeyboardInterrupt:
    print("\nStopping servers...")
finally:
    mtls_server.shutdown()
    https_server.shutdown()
    mtls_server.server_close()
    https_server.server_close()
