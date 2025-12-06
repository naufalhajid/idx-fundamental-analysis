from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependency_injections.db import get_db
from repositories.key_analysis_repository import KeyAnalysisRepository
from schemas.key_analysis import KeyAnalysis as KeyAnalysisSchema


router = APIRouter(tags=["key_analysis"], prefix="/key-analyses")


@router.get("/{ticker}/latest", response_model=KeyAnalysisSchema)
async def get_key_analysis_by_ticker(
    ticker: str, db: AsyncSession = Depends(get_db)
) -> KeyAnalysisSchema:
    repository = KeyAnalysisRepository(db)
    key_analysis = await repository.get_by_stock_ticker(ticker)
    if key_analysis is None:
        raise HTTPException(status_code=404, detail="Key analysis not found")

    return KeyAnalysisSchema.from_orm(key_analysis)
