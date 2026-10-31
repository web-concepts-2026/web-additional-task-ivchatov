"""
Basic HTTP server built only on the `socket` module (no HTTP libraries).

Run:  python server.py        -> http://localhost:9000
      python server.py 8080   -> custom port
"""

import json
import os
import socket
import sys
import threading

PORT = 9000
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

STATUS = {200: "OK", 201: "Created", 400: "Bad Request", 404: "Not Found"}
CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}

messages = []


# ---------- parsing ----------

def url_decode(s):
    """'%D0%86van+I' -> 'Іvan I'"""
    s = s.replace("+", " ")
    parts = s.split("%")
    result = parts[0].encode()
    for part in parts[1:]:
        try:
            result += bytes.fromhex(part[:2]) + part[2:].encode()
        except ValueError:
            result += ("%" + part).encode()
    return result.decode(errors="replace")


def parse_query(query):
    """'id=5&name=Ivan' -> {'id': '5', 'name': 'Ivan'}"""
    params = {}
    for pair in query.split("&"):
        if pair:
            key, _, value = pair.partition("=")
            params[url_decode(key)] = url_decode(value)
    return params


def parse_request(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return None
        data += chunk

    head, _, body = data.partition(b"\r\n\r\n")
    request_line, *header_lines = head.decode().split("\r\n")

    # request line: GET /page?id=5 HTTP/1.1
    method, target, version = request_line.split(" ")
    path, _, query = target.partition("?")

    # headers: "Name: value"
    headers = {}
    for line in header_lines:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()

    # body: read until Content-Length bytes are received
    length = int(headers.get("content-length", 0))
    while len(body) < length:
        body += conn.recv(4096)

    return {
        "method": method,
        "path": url_decode(path),
        "version": version,
        "query": parse_query(query),
        "headers": headers,
        "body": body[:length],
    }


# ---------- responses ----------

def response(status, body, content_type="text/plain"):
    if isinstance(body, str):
        body = body.encode()
    head = (
        f"HTTP/1.1 {status} {STATUS[status]}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return head.encode() + body


def json_response(status, data):
    return response(status, json.dumps(data, ensure_ascii=False, indent=2), "application/json")


# ---------- handlers ----------

def serve_static(req):
    filename = req["path"].lstrip("/") or "index.html"
    filepath = os.path.join(STATIC_DIR, filename)
    if ".." in filename or not os.path.isfile(filepath):
        return response(404, "404 Not Found")
    with open(filepath, "rb") as f:
        ext = os.path.splitext(filepath)[1]
        return response(200, f.read(), CONTENT_TYPES.get(ext, "text/plain"))


def page(req):
    """GET /page?id=5"""
    page_id = req["query"].get("id")
    if page_id is None:
        return response(400, "Missing query parameter 'id'")
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in req["query"].items())
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="/style.css"></head>
<body><main>
<h1>You requested page #{page_id}</h1>
<table><tr><th>Key</th><th>Value</th></tr>{rows}</table>
<p><a href="/">&larr; Back home</a></p>
</main></body></html>"""
    return response(200, html, "text/html")


def show_headers(req):
    """GET /headers - shows what was parsed from the request"""
    return json_response(200, {k: req[k] for k in ("method", "path", "version", "query", "headers")})


def get_messages(req):
    """GET /api/messages"""
    return json_response(200, messages)


def add_message(req):
    """POST /api/messages  body: {"name": "...", "text": "..."}"""
    try:
        data = json.loads(req["body"])
    except ValueError:
        return json_response(400, {"error": "Invalid JSON"})
    message = {"id": len(messages) + 1, "name": data.get("name"), "text": data.get("text")}
    messages.append(message)
    return json_response(201, {"status": "created", "message": message})


ROUTES = {
    ("GET", "/page"): page,
    ("GET", "/headers"): show_headers,
    ("GET", "/api/messages"): get_messages,
    ("POST", "/api/messages"): add_message,
}


# ---------- server ----------

def handle_client(conn, addr):
    with conn:
        req = parse_request(conn)
        if req is None:
            return
        handler = ROUTES.get((req["method"], req["path"]))
        if handler:
            resp = handler(req)
        elif req["method"] == "GET":
            resp = serve_static(req)
        else:
            resp = json_response(404, {"error": "Not found"})
        print(f"{addr[0]} {req['method']} {req['path']} -> {resp.split()[1].decode()}")
        conn.sendall(resp)


def run(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen()
    print(f"Serving on http://localhost:{port}  (Ctrl+C to stop)")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
