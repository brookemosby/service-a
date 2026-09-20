import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from app.database import Base, engine, get_db
from app.models import Item

SERVICE_NAME = os.getenv("SERVICE_NAME", "service-a")
API_PREFIX = os.getenv("API_PREFIX", "")

app = FastAPI(title=SERVICE_NAME)
router = APIRouter(prefix=API_PREFIX)


class ItemCreate(BaseModel):
    name: str
    description: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ItemRead(BaseModel):
    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


@app.on_event("startup")
def create_schema_and_tables():
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS service_a")
        conn.commit()
    Base.metadata.create_all(bind=engine)


@router.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@router.get("/items", response_model=list[ItemRead])
def list_items(db=Depends(get_db)):
    return db.query(Item).order_by(Item.id).all()


@router.post("/items", response_model=ItemRead, status_code=201)
def create_item(payload: ItemCreate, db=Depends(get_db)):
    item = Item(name=payload.name, description=payload.description)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/items/{item_id}", response_model=ItemRead)
def get_item(item_id, db=Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.put("/items/{item_id}", response_model=ItemRead)
def update_item(item_id, payload: ItemUpdate, db=Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if payload.name is not None:
        item.name = payload.name
    if payload.description is not None:
        item.description = payload.description
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id, db=Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()


app.include_router(router)
