from __future__ import annotations
import asyncio
import hashlib
import ipaddress
import json
import math
import time
from collections import OrderedDict, deque
from threading import Lock
from redis.asyncio import Redis
from redis.exceptions import RedisError
from app.core.config import settings


class RequestControlsMiddleware:
    def __init__(self, app):
        self.app = app
        self._lock = Lock()
        self._requests = OrderedDict()
        self._redis = None

    def _headers(self, scope):
        return {k.lower(): v for k, v in scope.get("headers", [])}

    def _content_length(self, scope):
        try:
            return max(0, int(self._headers(scope).get(b"content-length", b"0")))
        except ValueError:
            return 0

    def _client_ip(self, scope):
        peer = (scope.get("client") or ("unknown",))[0]
        networks = [ipaddress.ip_network(cidr) for cidr in settings.trusted_proxy_cidrs]
        def trusted(value):
            try:
                return any(ipaddress.ip_address(value) in net for net in networks)
            except ValueError:
                return False
        if not trusted(peer):
            return peer
        # Walk from the trusted peer to the first untrusted hop, never blindly
        # using a client-supplied leftmost value. Uvicorn proxy parsing is off.
        chain = self._headers(scope).get(b"x-forwarded-for", b"").decode("latin1").split(",")
        current = peer
        for hop in reversed(chain):
            if not trusted(current):
                break
            try:
                current = str(ipaddress.ip_address(hop.strip()))
            except ValueError:
                return peer
        return current

    def _local_limit(self, key, limit):
        if limit <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            while self._requests and next(iter(self._requests.values()))[-1] <= now - 60:
                self._requests.popitem(last=False)
            if key not in self._requests and len(self._requests) >= 10000:
                return 60
            requests = self._requests.setdefault(key, deque())
            self._requests.move_to_end(key)
            while requests and requests[0] <= now - 60:
                requests.popleft()
            if len(requests) >= limit:
                return max(1, math.ceil(60 - (now - requests[0])))
            requests.append(now)
        return None

    def _bucket(self, scope):
        login = scope.get("path", "").rstrip("/") == "/api/auth/login"
        return ("login" if login else "api", settings.auth_rate_limit_per_minute if login else settings.api_rate_limit_per_minute)

    def _rate_limit_retry_after(self, scope):
        bucket, limit = self._bucket(scope)
        return self._local_limit((self._client_ip(scope), bucket), limit)

    async def _limit(self, key, limit):
        if limit <= 0:
            return None
        if not settings.rate_limit_redis_url:
            return self._local_limit(key, limit)
        if self._redis is None:
            self._redis = Redis.from_url(settings.rate_limit_redis_url, socket_connect_timeout=2, socket_timeout=2)
        redis_key = "rfq:rate:" + hashlib.sha256(str(key).encode()).hexdigest()
        count, ttl = await self._redis.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return {n,redis.call('TTL',KEYS[1])}",
            1, redis_key,
        )
        return max(1, ttl) if count > limit else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/") or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        if self._content_length(scope) > settings.api_max_body_bytes:
            await self._send_json(send, 413, "Request body is too large.")
            return
        bucket, limit = self._bucket(scope)
        try:
            retry = await self._limit((self._client_ip(scope), bucket), limit)
            if retry:
                await self._send_json(send, 429, "Too many requests. Please retry shortly.", {"Retry-After": str(retry)})
                return
            body = bytearray()
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > settings.api_max_body_bytes:
                        await self._send_json(send, 413, "Request body is too large.")
                        return
                    if not message.get("more_body", False):
                        break
            if bucket == "login":
                try:
                    payload = json.loads(body)
                    email = payload.get("email", "") if isinstance(payload, dict) else ""
                    if isinstance(email, str):
                        account_key = hashlib.sha256(email.strip().lower().encode()).hexdigest()
                        retry = await self._limit(("account", account_key), limit)
                        if retry:
                            await self._send_json(send, 429, "Too many requests. Please retry shortly.", {"Retry-After": str(retry)})
                            return
                except (ValueError, UnicodeError):
                    pass
        except RedisError:
            await self._send_json(send, 503, "Request protection is temporarily unavailable. Please retry.", {"Retry-After": "5"})
            return
        except TimeoutError:
            await self._send_json(send, 408, "Request body timed out.")
            return
        delivered = False
        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, buffered_receive, send)

    async def _send_json(self, send, status_code, detail, headers=None):
        body = json.dumps({"detail": detail}).encode()
        raw = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        raw.extend((k.lower().encode(), v.encode()) for k, v in (headers or {}).items())
        await send({"type": "http.response.start", "status": status_code, "headers": raw})
        await send({"type": "http.response.body", "body": body})
