import pathlib
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import nats
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agents.registry import load_domain_config, start_agents, stop_agents
from api.config import Settings
from api.db.pool import close_pool, create_pool
from api.llm.client import LLMClient

settings = Settings()

# Suppress uvicorn access logs that flood stdout and hide startup messages
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await logger.ainfo("biocoach_api_starting")
    app.state.nc = None
    app.state.agents = []
    app.state.domain_config = {}

    try:
        app.state.pool = await create_pool(settings.DATABASE_URL)

        # Load system prompt from file
        prompt_path = pathlib.Path(__file__).resolve().parent.parent / "prompts" / "health_advisor.md"
        app.state.system_prompt = prompt_path.read_text(encoding="utf-8")
        await logger.ainfo("system_prompt_loaded", chars=len(app.state.system_prompt))

        # Initialize LLM client
        app.state.llm_client = LLMClient(
            base_url=settings.LITELLM_BASE_URL,
            api_key=settings.LITELLM_API_KEY,
        )
        await logger.ainfo("llm_client_initialized", base_url=settings.LITELLM_BASE_URL)

        # Load domain config from DB
        try:
            app.state.domain_config = await load_domain_config(
                app.state.pool, settings.DEFAULT_DOMAIN_TYPE
            )
            await logger.ainfo("domain_config_loaded", domain_type=settings.DEFAULT_DOMAIN_TYPE)
        except Exception:
            await logger.aexception("domain_config_load_failed")

        # Connect to NATS and start agents
        try:
            app.state.nc = await nats.connect(settings.NATS_URL)
            await logger.ainfo("nats_connected", url=settings.NATS_URL)

            app.state.agents = await start_agents(
                app.state.nc,
                app.state.domain_config,
                domain_id="*",
                llm_client=app.state.llm_client,
            )
        except Exception:
            await logger.aexception("nats_startup_failed")
            app.state.nc = None
            app.state.agents = []

        await logger.ainfo("api_startup_complete")
        yield
    finally:
        # Stop agents
        if app.state.agents:
            await stop_agents(app.state.agents)

        # Close NATS connection
        if app.state.nc is not None and not app.state.nc.is_closed:
            await app.state.nc.close()
            await logger.ainfo("nats_disconnected")

        if hasattr(app.state, "pool"):
            await close_pool(app.state.pool)
        await logger.ainfo("biocoach_api_shutting_down")


app = FastAPI(title="BioCoach API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from api.auth.router import router as auth_router
from api.chat.router import router as chat_router

app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
