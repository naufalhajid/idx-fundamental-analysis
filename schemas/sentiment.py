from dataclasses import dataclass
from datetime import datetime

from schemas import BaseDataClass


@dataclass
class Sentiment(BaseDataClass):
    content: str = ""
    rate: float = 0.0
    category: str = ""
    posted_at: datetime = None
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
