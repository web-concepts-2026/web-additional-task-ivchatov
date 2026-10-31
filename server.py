""" Run:
    python3 server.py            # listens on 0.0.0.0:8080
    python3 server.py 9000       # custom port
"""

import json
import os
import socket
import sys
import threading
from datetime import datetime, timezone

HOST = "0.0.0.0"
PORT = 8080
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
RECV_SIZE = 4096
MAX_HEADER_SIZE = 64 * 1024

STATUS_TEXT = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    415: "Unsupported Media Type",
    500: "Internal Server Error",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

MESSAGES = []
MESSAGES_LOCK = threading.Lock()


def url_decode(s):
    """Decode %XX escapes and '+' (as space) — a small replacement for urllib.parse.unquote_plus."""
    s = s.replace("+", " ")
    out = bytearray()
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "%" and i + 2 < len(s):
            hex_part = s[i + 1:i + 3]
            try:
                out.append(int(hex_part, 16))
                i += 3
                continue
            except ValueError:
                pass
        out.extend(ch.encode("utf-8"))
        i += 1
    return out.decode("utf-8", errors="replace")


def parse_query(query_string):
    """'id=5&name=Ivan&tag=a&tag=b' -> {'id': '5', 'name': 'Ivan', 'tag': ['a', 'b']}"""
    params = {}
    if not query_string:
        return params
    for pair in query_string.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        key, value = url_decode(key), url_decode(value)
        if key in params:
            if isinstance(params[key], list):
                params[key].append(value)
            else:
                params[key] = [params[key], value]
        else:
            params[key] = value
    return params


class HTTPRequest:
    def __init__(self, method, target, version, headers, body):
        self.method = method
        self.target = target        
        self.version = version
        self.headers = headers       
        self.body = body             

        path, _, query = target.partition("?")
        self.path = url_decode(path)
        self.query_string = query
        self.query = parse_query(query)

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else None

    def __repr__(self):
        return f"<HTTPRequest {self.method} {self.path} query={self.query}>"


class BadRequest(Exception):
    pass


def read_request(conn):
    """Read one full HTTP request from the socket and return an HTTPRequest (or None if closed)."""
    data = b""
 
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(RECV_SIZE)
        if not chunk:
            if not data:
                return None
            raise BadRequest("Connection closed before headers were complete")
        data += chunk
        if len(data) > MAX_HEADER_SIZE:
            raise BadRequest("Headers too large")

    head, _, rest = data.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")

 
    parts = lines[0].split(" ")
    if len(parts) != 3:
        raise BadRequest(f"Malformed request line: {lines[0]!r}")
    method, target, version = parts
    if not version.startswith("HTTP/"):
        raise BadRequest("Invalid HTTP version")

  
    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise BadRequest(f"Malformed header line: {line!r}")
        name, _, value = line.partition(":")
        name = name.strip().lower()
        value = value.strip()
 
        headers[name] = f"{headers[name]}, {value}" if name in headers else value

 
    body = rest
    length_header = headers.get("content-length")
    if length_header is not None:
        try:
            length = int(length_header)
        except ValueError:
            raise BadRequest("Invalid Content-Length")
        while len(body) < length:
            chunk = conn.recv(RECV_SIZE)
            if not chunk:
                raise BadRequest("Body shorter than Content-Length")
            body += chunk
        body = body[:length]
    else:
        body = b""

    return HTTPRequest(method.upper(), target, version, headers, body)




def build_response(status, body=b"", content_type="text/plain; charset=utf-8", extra_headers=None):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = {
        "Date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Server": "PySocketServer/1.0",
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Connection": "close",
    }
    if extra_headers:
        headers.update(extra_headers)
    status_line = f"HTTP/1.1 {status} {STATUS_TEXT.get(status, '')}\r\n"
    header_block = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    return (status_line + header_block + "\r\n").encode("utf-8") + body


def json_response(status, obj):
    return build_response(status, json.dumps(obj, ensure_ascii=False, indent=2),
                          "application/json; charset=utf-8")


def html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))




def serve_static(req):
    rel = req.path.lstrip("/") or "index.html"
    full = os.path.realpath(os.path.join(STATIC_DIR, rel))

    if not full.startswith(os.path.realpath(STATIC_DIR) + os.sep):
        return build_response(403, "403 Forbidden")
    if os.path.isdir(full):
        full = os.path.join(full, "index.html")
    if not os.path.isfile(full):
        return build_response(404, "<h1>404 Not Found</h1>", "text/html; charset=utf-8")
    ext = os.path.splitext(full)[1].lower()
    with open(full, "rb") as f:
        content = f.read()
    return build_response(200, content, CONTENT_TYPES.get(ext, "application/octet-stream"))


def handle_page(req):
    """GET /page?id=5 — demonstrates query parameters."""
    page_id = req.query.get("id")
    if page_id is None:
        return build_response(400, "<h1>400</h1><p>Missing query parameter <code>id</code></p>",
                              "text/html; charset=utf-8")
    rows = "".join(f"<tr><td>{html_escape(k)}</td><td>{html_escape(v)}</td></tr>"
                   for k, v in req.query.items())
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Page {html_escape(page_id)}</title>
<link rel="stylesheet" href="/style.css"></head>
<body><main>
<h1>You requested page #{html_escape(page_id)}</h1>
<h2>All query parameters</h2>
<table><tr><th>Key</th><th>Value</th></tr>{rows}</table>
<p><a href="/">&larr; Back home</a></p>
</main></body></html>"""
    return build_response(200, html, "text/html; charset=utf-8")


def handle_headers(req):
    """GET /headers — echoes back everything that was parsed from the request."""
    return json_response(200, {
        "method": req.method,
        "path": req.path,
        "version": req.version,
        "query": req.query,
        "headers": req.headers,
    })


def handle_echo(req):
    """POST /echo — parses the body according to Content-Type and returns it."""
    ctype = req.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype == "application/json":
        try:
            parsed = req.json()
        except (ValueError, UnicodeDecodeError) as e:
            return json_response(400, {"error": f"Invalid JSON: {e}"})
    elif ctype == "application/x-www-form-urlencoded":
        parsed = parse_query(req.body.decode("utf-8", errors="replace"))
    else:
        parsed = req.body.decode("utf-8", errors="replace")
    return json_response(200, {
        "received": parsed,
        "content_type": ctype or None,
        "content_length": len(req.body),
        "query": req.query,
    })


def handle_messages_post(req):
    """POST /api/messages — expects JSON {"name": "...", "text": "..."} and stores it."""
    ctype = req.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != "application/json":
        return json_response(415, {"error": "Content-Type must be application/json"})
    try:
        data = req.json()
    except (ValueError, UnicodeDecodeError) as e:
        return json_response(400, {"error": f"Invalid JSON: {e}"})
    if not isinstance(data, dict) or not data.get("name") or not data.get("text"):
        return json_response(400, {"error": "JSON must contain non-empty 'name' and 'text'"})
    with MESSAGES_LOCK:
        msg = {"id": len(MESSAGES) + 1, "name": str(data["name"]), "text": str(data["text"]),
               "created_at": datetime.now(timezone.utc).isoformat()}
        MESSAGES.append(msg)
    return json_response(201, {"status": "created", "message": msg})


def handle_messages_get(req):
    with MESSAGES_LOCK:
        return json_response(200, {"count": len(MESSAGES), "messages": list(MESSAGES)})


ROUTES = {
    ("GET", "/page"): handle_page,
    ("GET", "/headers"): handle_headers,
    ("GET", "/api/messages"): handle_messages_get,
    ("POST", "/echo"): handle_echo,
    ("POST", "/api/messages"): handle_messages_post,
}


def dispatch(req):
    handler = ROUTES.get((req.method, req.path))
    if handler:
        return handler(req)
    if req.method in ("GET", "HEAD"):
        resp = serve_static(req)
        if req.method == "HEAD":                     
            resp = resp.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
        return resp

    allowed = sorted(m for (m, p) in ROUTES if p == req.path)
    if allowed:
        return build_response(405, "405 Method Not Allowed",
                              extra_headers={"Allow": ", ".join(allowed)})
    return json_response(404, {"error": f"No route for {req.method} {req.path}"})




def handle_client(conn, addr):
    with conn:
        conn.settimeout(10)
        try:
            req = read_request(conn)
            if req is None:
                return
            response = dispatch(req)
            status = response.split(b" ", 2)[1].decode()
            print(f"[{datetime.now():%H:%M:%S}] {addr[0]} {req.method} {req.target} -> {status}")
        except BadRequest as e:
            response = build_response(400, f"400 Bad Request: {e}")
            print(f"[{datetime.now():%H:%M:%S}] {addr[0]} bad request: {e}")
        except socket.timeout:
            return
        except Exception as e: 
            response = build_response(500, "500 Internal Server Error")
            print(f"[{datetime.now():%H:%M:%S}] {addr[0]} error: {e!r}")
        try:
            conn.sendall(response)
        except OSError:
            pass


def run(host=HOST, port=PORT):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(16)
    print(f"Serving on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.close()


if __name__ == "__main__":
    run(port=int(sys.argv[1]) if len(sys.argv) > 1 else PORT)
