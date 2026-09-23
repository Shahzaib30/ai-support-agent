from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes import conversations, health, ingest, stats
from connectors.web import router as web_connector
from connectors.whatsapp import router as whatsapp_connector
from database.conversations import restore_active_conversation_count
from database.pool import connect, disconnect

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")

    await connect()
    count = await restore_active_conversation_count()
    logger.info(f"Restored {count} conversations to gauge")
    logger.success("Startup complete")

    yield

    await disconnect()
    logger.info("Shutdown complete")


app = FastAPI(title="AI Support Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, include_in_schema=False)

app.include_router(web_connector.router)
app.include_router(whatsapp_connector.router)
app.include_router(health.router)
app.include_router(stats.router)
app.include_router(conversations.router)
app.include_router(ingest.router)


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=True,
    )
