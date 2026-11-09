from __future__ import annotations

import json
import math
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Awaitable, Callable

from app.core.config import settings

Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


class RequestBodyTooLarge(Exception):
    pass


class RequestControlsMiddleware:
    def __init__(self, app) -> None:
        self.app = app
        self._lock = Lock()
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def __call__(self, scope: dict, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        if path == "/health" or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        max_body_bytes = settings.api_max_body_bytes
        if max_body_bytes > 0 and self._content_length(scope) > max_body_bytes:
            await self._send_json(send, 413, "Request body is too large.")
            return

        retry_after = self._rate_limit_retry_after(scope)
        if retry_after is not None:
            await self._send_json(
                send,
                429,
                "Too many requests. Please retry shortly.",
                headers={"Retry-After": str(retry_after)},
            )
            return

        try:
            await self.app(scope, self._limited_receive(receive, max_body_bytes), send)
        except RequestBodyTooLarge:
            await self._send_json(send, 413, "Request body is too large.")

    def _content_length(self, scope: dict) -> int:
        headers = self._headers(scope)
        try:
            return int(headers.get(b"content-length", b"0"))
        except ValueError:
            return 0

    def _headers(self, scope: dict) -> dict[bytes, bytes]:
        return {key.lower(): value for key, value in scope.get("headers", [])}

    def _client_ip(self, scope: dict) -> str:
        headers = self._headers(scope)
        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            return forwarded_for.decode("latin1").split(",", 1)[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _rate_limit_retry_after(self, scope: dict) -> int | None:
        path = scope.get("path", "")
        if not path.startswith("/api/"):
            return None

        bucket = "auth-login" if path == "/api/auth/login" else "api"
        limit = settings.auth_rate_limit_per_minute if bucket == "auth-login" else settings.api_rate_limit_per_minute
        if limit <= 0:
            return None

        now = time.monotonic()
        window_seconds = 60
        key = (self._client_ip(scope), bucket)

        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= now - window_seconds:
                requests.popleft()
            if len(requests) >= limit:
                return max(1, math.ceil(window_seconds - (now - requests[0])))
            requests.append(now)

        return None

    def _limited_receive(self, receive: Receive, max_body_bytes: int) -> Receive:
        size = 0

        async def limited_receive() -> dict:
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if max_body_bytes > 0 and size > max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        return limited_receive

    async def _send_json(
        self,
        send: Send,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps({"detail": detail}).encode("utf-8")
        raw_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        for key, value in (headers or {}).items():
            raw_headers.append((key.lower().encode("ascii"), value.encode("ascii")))

        await send({"type": "http.response.start", "status": status_code, "headers": raw_headers})
        await send({"type": "http.response.body", "body": body})
