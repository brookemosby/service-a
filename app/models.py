from sqlalchemy import Column, Integer, String

from app.database import Base


class Item(Base):
    __tablename__ = "items"
    __table_args__ = {"schema": "service_a"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
