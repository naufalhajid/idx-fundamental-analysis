from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependency_injections.db import get_db
from repositories.fundamental_repository import FundamentalRepository
from schemas.fundamental import Fundamental as FundamentalSchema


router = APIRouter(tags=["fundamentals"], prefix="/fundamentals")


@router.get("/{ticker}/latest", response_model=FundamentalSchema)
async def get_fundamental_by_ticker(
    ticker: str, db: AsyncSession = Depends(get_db)
) -> FundamentalSchema:
    repository = FundamentalRepository(db)
    fundamental = await repository.get_by_stock_ticker(ticker)
    if fundamental is None:
        raise HTTPException(status_code=404, detail="Fundamental not found")

    return FundamentalSchema.from_orm(fundamental)
