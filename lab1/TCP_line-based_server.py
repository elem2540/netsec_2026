import socket
import threading

HOST = "0.0.0.0"
PORT = 9001

store = {}
store_lock = threading.Lock()


def process_command(command):
    if command == "PING":
        return "PONG"

    if command.startswith("ECHO "):
        return command[5:]

    if command.startswith("SET "):
        parts = command[4:].split(" ", 1)

        if len(parts) != 2 or not parts[0] or not parts[1]:
            return "ERR"

        key, value = parts

        with store_lock:
            store[key] = value

        return "OK"

    if command.startswith("GET "):
        key = command[4:]

        if not key or " " in key:
            return "ERR"

        with store_lock:
            return store.get(key, "NOT_FOUND")

    return "ERR"


def handle_client(conn, addr):
    print(f"Client connected: {addr}")

    buffer = b""

    try:
        with conn:
            while True:
                data = conn.recv(1024)

                if not data:
                    break

                buffer += data

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)

                    try:
                        command = line.decode("ascii")
                        response = process_command(command)
                    except UnicodeDecodeError:
                        response = "ERR"

                    conn.sendall(
                        (response + "\n").encode("ascii")
                    )
    except OSError as e:
        print(f"Client error {addr}: {e}")

    print(f"Client disconnected: {addr}")


if __name__ == "__main__":
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, PORT))
        server.listen()

        print(f"Server listening on {HOST}:{PORT}")

        while True:
            conn, addr = server.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            client_thread.start()
