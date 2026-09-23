from fastapi import APIRouter, HTTPException
from loguru import logger

router = APIRouter()


@router.post("/ingest")
async def ingest_documents():
    try:
        from rag.ingest import ingest
        return ingest()
    except Exception as e:
        logger.error(f"Error ingesting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
