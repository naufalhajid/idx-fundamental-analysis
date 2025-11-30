import logging
import os

from sqlalchemy import create_engine

from db.models import Base
from db.models.fundamental import *
from db.models.key_analysis import KeyAnalysis
from db.models.sentiment import Sentiment
from db.models.stock import Stock
from db.models.stock_price import StockPrice
from utils.helpers import get_project_root
from utils.logger_config import InterceptHandler

# Set the base directory to the project root
base_dir = get_project_root()

# Define the path to the database file relative to the project root
db_path = os.path.join(base_dir, "db/idx-fundamental.db")

logging.basicConfig(handlers=[InterceptHandler()], level=0)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


class DB:
    def __init__(self):
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)

    def setup_db(self, is_drop_table: bool = False):
        with self._engine.begin() as conn:
            if is_drop_table:
                # Drop all tables in the database
                Base.metadata.drop_all(conn)

            # Create all tables in the database
            Base.metadata.create_all(conn)

    @property
    def engine(self):
        return self._engine


database = DB()
