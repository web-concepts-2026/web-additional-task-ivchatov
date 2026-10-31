# Basic HTTP server on raw sockets

A minimal HTTP/1.1 server written in Python using **only the `socket` standard library module** — no web frameworks and no HTTP libraries (`http.server`, `urllib`, `requests`, etc.).

## Features

- Listens on a port (default **8080**) and accepts incoming TCP connections (one thread per client)
- Parses the HTTP request manually:
  - **request line** → method, path, HTTP version
  - **headers** → dictionary (case-insensitive names, repeated headers joined)
  - **query parameters** → `/page?id=5&tag=a&tag=b` → `{"id": "5", "tag": ["a", "b"]}` (with `%XX` / `+` decoding)
  - **body** → read exactly `Content-Length` bytes
- **GET** – serves static files (HTML/CSS/JS/images) from `static/`, handles query parameters, protects against path traversal
- **POST** – parses the body (`application/json`, `application/x-www-form-urlencoded`) and responds with JSON
- Proper status codes: `200`, `201`, `400`, `403`, `404`, `405`, `415`, `500`

## Run

```bash
python3 server.py          # http://localhost:8080
python3 server.py 9000     # custom port
```

Requires Python 3.8+. No dependencies.

## Endpoints

| Method | Path            | Description |
|--------|-----------------|-------------|
| GET    | `/`             | Static `index.html` (+ `style.css`) |
| GET    | `/page?id=5`    | HTML page built from query parameters (`400` if `id` is missing) |
| GET    | `/headers`      | JSON with the parsed method, path, version, query and headers |
| GET    | `/api/messages` | List of messages stored in memory |
| POST   | `/api/messages` | Body `{"name": "...", "text": "..."}` (`application/json`) → `201 Created` |
| POST   | `/echo`         | Returns the parsed body (JSON / form / plain text) |

## Examples

```bash
# GET static file
curl -i http://localhost:8080/

# GET with query parameters
curl "http://localhost:8080/page?id=5&name=Ivan"

# Parsed headers
curl http://localhost:8080/headers -H "X-Custom: hello"

# POST JSON body
curl -i -X POST http://localhost:8080/api/messages \
     -H "Content-Type: application/json" \
     -d '{"name": "Ivan", "text": "Hello!"}'

# Echo any body
curl -X POST http://localhost:8080/echo -H "Content-Type: application/json" -d '{"a": [1, 2, 3]}'
```

The home page also contains a small form that sends a JSON `POST` request with `fetch()`.

## How it works

1. `socket.socket(AF_INET, SOCK_STREAM)` → `bind` → `listen` → `accept` in a loop.
2. For every connection `read_request()` receives bytes until `\r\n\r\n`, splits the request line and headers, then keeps reading until the body reaches `Content-Length`.
3. `dispatch()` picks a handler by `(method, path)`; unknown GET paths fall back to static files.
4. `build_response()` assembles the status line, headers (`Content-Type`, `Content-Length`, `Date`, …) and body, which are sent back with `sendall()`.
