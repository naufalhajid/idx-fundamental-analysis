from fastapi import APIRouter

from app.api.routers.health import router as health_router
from app.api.routers.stocks import router as stocks_router
from app.api.routers.fundamentals import router as fundamentals_router
from app.api.routers.key_analysis import router as key_analysis_router
from app.api.routers.stock_prices import router as stock_prices_router
from app.api.routers.sentiments import router as sentiments_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(stocks_router)
api_router.include_router(fundamentals_router)
api_router.include_router(key_analysis_router)
api_router.include_router(stock_prices_router)
api_router.include_router(sentiments_router)
