from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from typing_extensions import Annotated

INT_PK = Annotated[int, mapped_column(primary_key=True)]
TIMESTAMP = Annotated[
    datetime,
    mapped_column(nullable=False, server_default=func.CURRENT_TIMESTAMP()),
]
UPDATED_TIMESTAMP = Annotated[
    datetime,
    mapped_column(
        nullable=False,
        server_default=func.CURRENT_TIMESTAMP(),
        onupdate=func.CURRENT_TIMESTAMP(),
    ),
]
VARCHAR = Annotated[str, mapped_column(default="")]
FLOAT = Annotated[float, mapped_column(default=0.0)]


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    __abstract__ = True  # This tells SQLAlchemy not to create a table for this class

    id: Mapped[INT_PK]
    created_at: Mapped[TIMESTAMP]
    updated_at: Mapped[UPDATED_TIMESTAMP]

    def save(self, session):
        session.add(self)
        session.commit()

    def delete(self, session):
        session.delete(self)
        session.commit()

    @classmethod
    def all(cls, session):
        stmt = select(cls)
        return session.scalars(stmt)

    @classmethod
    def find_by_id(cls, session, id):
        stmt = select(cls).where(cls.id == id)
        return session.scalars(stmt).first()
