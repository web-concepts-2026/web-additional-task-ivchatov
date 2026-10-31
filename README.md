# Basic HTTP server on raw sockets

A minimal HTTP/1.1 server written in Python using **only the `socket` standard library module** — no web frameworks and no HTTP libraries.

## Features

- Listens on a port (default **9000**) and accepts TCP connections (one thread per client)
- Parses the HTTP request manually: method, path, version, headers, query parameters and body (`Content-Length`)
- **GET** – serves static files (HTML/CSS) from `static/` and handles query parameters (`/page?id=5`)
- **POST** – parses a JSON body (`application/json`) and responds with JSON

## Run

```bash
python server.py          # http://localhost:9000
python server.py 8080     # custom port
```

Requires Python 3.8+. No dependencies.

> On Windows port 8080 may be reserved by the system (`WinError 10013`), that's why the default port is 9000.

## Endpoints

| Method | Path            | Description |
|--------|-----------------|-------------|
| GET    | `/`             | Static `index.html` (+ `style.css`) |
| GET    | `/page?id=5`    | HTML page built from query parameters (`400` if `id` is missing) |
| GET    | `/headers`      | JSON with the parsed method, path, version, query and headers |
| GET    | `/api/messages` | List of saved messages |
| POST   | `/api/messages` | JSON body `{"name": "...", "text": "..."}` → `201 Created` |

## Examples

```bash
curl -i http://localhost:9000/
curl "http://localhost:9000/page?id=5&name=Ivan"
curl http://localhost:9000/headers -H "X-Custom: hello"
curl -i -X POST http://localhost:9000/api/messages \
     -H "Content-Type: application/json" \
     -d '{"name": "Ivan", "text": "Hello!"}'
```

## How it works

1. `socket()` → `bind()` → `listen()` → `accept()` in a loop.
2. `parse_request()` receives bytes until `\r\n\r\n`, splits the request line and headers, then reads the body up to `Content-Length`.
3. `ROUTES` maps `(method, path)` to a handler; other GET paths are served from `static/`.
4. `response()` builds the status line, headers and body and sends them back with `sendall()`.
