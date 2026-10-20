from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

HOST = "0.0.0.0"
PORT = 8080

notes = {}
next_id = 1


class CMyHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/":
            self.send_response(200)
            self.end_headers()

        elif parsed_url.path == "/echo":
            params = parse_qs(parsed_url.query, keep_blank_values=True)
            msg = params.get("msg", [""])[0]

            response = {"msg": msg}
            body = json.dumps(response).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        elif parsed_url.path.startswith("/notes/"):
            id_str = parsed_url.path.split("/")[-1]

            if not id_str.isdigit():
                self.send_response(404)
                self.end_headers()
                return

            note_id = int(id_str)

            if note_id not in notes:
                self.send_response(404)
                self.end_headers()
                return

            response = {
                "id": note_id,
                "text": notes[note_id]
            }

            body = json.dumps(response).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global next_id

        parsed_url = urlparse(self.path)

        if parsed_url.path == "/notes":

            content_type = self.headers.get("Content-Type", "")

            if content_type != "application/json":
                self.send_response(415)
                self.end_headers()
                return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_response(400)
                self.end_headers()
                return

            if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                self.send_response(400)
                self.end_headers()
                return

            notes[next_id] = data["text"]

            response = {"id": next_id}
            next_id += 1

            body = json.dumps(response).encode("utf-8")

            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path.startswith("/notes/"):
            id_str = parsed_url.path.split("/")[-1]

            if not id_str.isdigit():
                self.send_response(404)
                self.end_headers()
                return

            note_id = int(id_str)

            if note_id not in notes:
                self.send_response(404)
                self.end_headers()
                return

            del notes[note_id]

            self.send_response(204)
            self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/notes" or parsed_url.path.startswith("/notes/"):
            self.send_response(405)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


server = HTTPServer((HOST, PORT), CMyHandler)

print(f"Server listenning on {PORT}")
server.serve_forever()
