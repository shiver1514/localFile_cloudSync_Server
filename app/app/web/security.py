from __future__ import annotations

import ipaddress
import os
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse


def _parse_nets(raw: str) -> list[ipaddress._BaseNetwork]:
    nets: list[ipaddress._BaseNetwork] = []
    for part in (raw or "").split(","):
        s = part.strip()
        if not s:
            continue
        try:
            nets.append(ipaddress.ip_network(s, strict=False))
        except ValueError as exc:
            raise ValueError(f"允许网段配置无效：{s}") from exc
    return nets


class NetworkAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_nets: Iterable[str]):
        super().__init__(app)
        self.allowed: list[ipaddress._BaseNetwork] = []
        self.allowlist_error: str | None = None
        try:
            self.allowed = _parse_nets(",".join(allowed_nets))
        except ValueError as exc:
            self.allowlist_error = str(exc)

    async def dispatch(self, request: Request, call_next):
        if self.allowlist_error:
            return PlainTextResponse(
                f"访问被拒绝：允许网段配置错误（{self.allowlist_error}）",
                status_code=503,
            )

        client_host = request.client.host if request.client else ""
        try:
            ip = ipaddress.ip_address(client_host)
        except Exception:
            return PlainTextResponse("访问被拒绝：来源地址无法识别", status_code=403)

        if self.allowed:
            ok = any(ip in net for net in self.allowed)
            if not ok:
                return PlainTextResponse("访问被拒绝：当前地址不在允许网段内", status_code=403)

        return await call_next(request)


def get_allowed_nets() -> list[str]:
    raw = os.environ.get("ALLOWED_NETS", "127.0.0.1/32")
    return [s.strip() for s in raw.split(",") if s.strip()]
