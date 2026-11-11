"""A local stand-in for api.okdata.online for tests: routes answer like the real API, every request
is recorded, and nothing leaves this machine. No real key is ever used."""
from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

TEST_KEY = "okd_test_0000000000000000"
Handler = Callable[[Dict[str, str]], Tuple[int, Dict[str, Any]]]


def ok(endpoint: str, *, items: Optional[List[Any]] = None, item: Any = None, next_cursor: Optional[str] = None,
       amount: str = "0.002") -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "code": "ok", "request_id": str(uuid.uuid4()), "warnings": [],
        "meta": {"capability": endpoint, "billing": {"amount": amount, "currency": "USD", "balance_after": "1"},
                 "unavailable": {}, "cached": False, "replayed": False, "fetched_at": "2026-11-12T08:00:00Z"},
    }
    if items is not None:
        body["data"] = {"items": items}
        body["page"] = {"next_cursor": next_cursor, "has_more": next_cursor is not None}
    else:
        body["data"] = {"item": item}
    return body


def error(code: str, *, retry: str = "no") -> Dict[str, Any]:
    return {"code": code, "message": "scripted", "request_id": str(uuid.uuid4()), "charged": False,
            "retry": retry, "retry_after_seconds": 0}


class MockOkdata:
    def __init__(self, routes: Dict[str, Handler], prices: Optional[Dict[str, str]] = None) -> None:
        self.routes = routes
        self.prices = prices or {}
        self.requests: List[Dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def paid(self) -> List[Dict[str, Any]]:
        return [r for r in self.requests if r["path"] != "/v1/catalog"]

    def _answer(self, path: str, query: Dict[str, str], headers: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
        if path == "/v1/catalog":
            endpoints = [{"id": k, "maxCharge": v} for k, v in self.prices.items()]
            return 200, {"code": "ok", "request_id": "c", "warnings": [], "data": {"endpoints": endpoints}}
        if headers.get("authorization") != f"Bearer {TEST_KEY}":
            return 401, error("unauthorized", retry="after_fix")
        route = self.routes.get(path)
        return route(query) if route else (404, error("unknown_endpoint"))

    def _handler(self) -> type:
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                query = dict(parse_qsl(parts.query))
                headers = {k.lower(): v for k, v in self.headers.items()}
                mock.requests.append({"path": parts.path, "query": query, "headers": headers})
                status, body = mock._answer(parts.path, query, headers)
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return H
