import asyncio
import hashlib
import ssl
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ProtocolNegotiated
from aioquic.h3.connection import H3Connection, H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived

HOST = "0.0.0.0"
PORT = 4433
CERT = "cert.pem"
KEY = "key.pem"


def handle_request(method, path, protocol, body=b""):
    if method == "GET" and path == "/":
        return 200, b"OK"

    elif method == "GET" and path == "/proto":
        return 200, protocol.encode("utf-8")

    elif method == "POST" and path == "/hash":
        hash_value = hashlib.sha256(body).hexdigest()
        return 200, hash_value.encode("utf-8")

    else:
        return 404, b"Not Found"


async def handle_https(reader, writer):
    request_line = await reader.readline()
    request_line = request_line.decode("utf-8")
    print("Request received:", request_line.strip())

    method, path, version = request_line.strip().split()
    print("Method:", method)
    print("Path:", path)
    print("Version:", version)

    headers = {}
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        name, value = line.decode("latin-1").split(":", 1)
        headers[name.strip().lower()] = value.strip()
    print("Headers:", headers)

    content_length = int(headers.get("content-length", "0"))
    body = await reader.readexactly(content_length)
    print("Body received:", body)

    status, response_body = handle_request(method, path, "HTTP/1.1", body)
    response_headers = (
        f"HTTP/1.1 {status} {'OK' if status == 200 else 'Not Found'}\r\n"
        f"Content-Type: text/plain\r\n"
        f"Content-Length: {len(response_body)}\r\n"
        f'Alt-Svc: h3=":4433"\r\n'
        f"Connection: close\r\n"
        f"\r\n"
    )

    response = response_headers.encode("utf-8") + response_body
    writer.write(response)
    await writer.drain()
    print("Response sent to the client")

    writer.close()
    await writer.wait_closed()


async def run_https():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT, KEY)
    context.set_alpn_protocols(["http/1.1"])

    server = await asyncio.start_server(
        handle_https,
        HOST,
        PORT,
        ssl=context
    )

    print(f"HTTPS server listening on a TCP port {PORT}")

    async with server:
        await server.serve_forever()


class HTTP3Protocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http = None
        self.streams = {}

    def finish_request(self, stream_id):
        stream = self.streams.pop(stream_id, None)
        if stream is None:
            return

        status, response_body = handle_request(
            stream["method"],
            stream["path"],
            "HTTP/3",
            bytes(stream["body"])
        )

        print("HTTP/3 response:", status)

        response_headers = [
            (b":status", str(status).encode("ascii")),
            (b"content-type", b"text/plain"),
            (b"content-length", str(len(response_body)).encode("ascii"))
        ]

        self.http.send_headers(
            stream_id=stream_id,
            headers=response_headers
        )

        self.http.send_data(
            stream_id=stream_id,
            data=response_body,
            end_stream=True
        )

        self.transmit()

    def handle_http_event(self, event):
        if isinstance(event, HeadersReceived):
            headers = dict(event.headers)
            method = headers.get(b":method", b"GET").decode("utf-8")
            path = headers.get(b":path", b"/").decode("utf-8")

            print("Stream ID:", event.stream_id)
            print("Method:", method)
            print("Path:", path)

            self.streams[event.stream_id] = {
                "method": method,
                "path": path,
                "body": bytearray()
            }

            print("Stream stored:", event.stream_id)
            if event.stream_ended:
                self.finish_request(event.stream_id)

        elif isinstance(event, DataReceived):
            stream = self.streams.get(event.stream_id)
            if stream is None:
                return

            stream["body"].extend(event.data)

            print("Data received on the stream:", event.stream_id)
            print("Body size:", len(stream["body"]))
            if event.stream_ended:
                self.finish_request(event.stream_id)

    def quic_event_received(self, event):
        if isinstance(event, ProtocolNegotiated):
            if event.alpn_protocol in H3_ALPN:
                self.http = H3Connection(self._quic)
                print("HTTP/3 connection initialized")

        if self.http is None:
            return

        for http_event in self.http.handle_event(event):
            self.handle_http_event(http_event)


async def run_http3():
    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=H3_ALPN
    )

    configuration.load_cert_chain(CERT, KEY)

    server = await serve(
        HOST,
        PORT,
        configuration=configuration,
        create_protocol=HTTP3Protocol
    )

    print(f"HTTP/3 server listening on UDP port {PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        server.close()


if __name__ == "__main__":
    async def start_servers():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(run_https())
            tg.create_task(run_http3())

    asyncio.run(start_servers())
