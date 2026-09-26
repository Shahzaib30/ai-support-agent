from fastapi import APIRouter
from database.stats import get_today_stats

router = APIRouter()

@router.get("/stats")
async def get_stats():
    return {"today": await get_today_stats()}
