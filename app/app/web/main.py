from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import load_config
from app.providers.feishu_legacy.db import init_db
from app.web.security import NetworkAllowlistMiddleware, get_allowed_nets
from app.web.api import router as api_router, start_scheduler, stop_scheduler
from app.web.pages import router as pages_router


def build_app() -> FastAPI:
    cfg = load_config()
    init_db(cfg.database.path)

    @asynccontextmanager
    async def lifespan(_api: FastAPI):
        start_scheduler()
        try:
            yield
        finally:
            await stop_scheduler()

    api = FastAPI(title="localFile_cloudSync_Server", version="0.1.0", lifespan=lifespan)
    api.add_middleware(NetworkAllowlistMiddleware, allowed_nets=get_allowed_nets())

    api.include_router(pages_router)

    api.include_router(api_router)
    return api


def main():
    import uvicorn

    cfg = load_config()
    init_db(cfg.database.path)

    from app.core.logging_setup import setup_logging

    setup_logging(cfg.logging.level, cfg.logging.file)

    uvicorn.run(
        build_app(),
        host=cfg.web_bind_host,
        port=cfg.web_port,
        log_level=cfg.logging.level.lower(),
        log_config=None,
    )


if __name__ == "__main__":
    main()
