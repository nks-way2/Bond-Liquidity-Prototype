
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
import asyncio

SQLALCHEMY_DATABASE_URL = "sqlite:///./db.sqlite3"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --------- Models ---------
class Bond(Base):
    __tablename__ = "bonds"
    id = Column(Integer, primary_key=True, index=True)
    isin = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    coupon = Column(Float, default=0.0)
    maturity = Column(String, default="")
    face_value = Column(Float, default=100.0)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    bond_id = Column(Integer, ForeignKey("bonds.id"))
    side = Column(String, index=True)  # "buy" or "sell"
    price = Column(Float, index=True)
    qty = Column(Float)  # face value units
    filled_qty = Column(Float, default=0.0)
    status = Column(String, default="open") # open, partial, filled, cancelled
    ts = Column(DateTime, default=datetime.utcnow)
    user = Column(String, default="demo")
    bond = relationship("Bond")

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    bond_id = Column(Integer, ForeignKey("bonds.id"))
    buy_order_id = Column(Integer, ForeignKey("orders.id"))
    sell_order_id = Column(Integer, ForeignKey("orders.id"))
    price = Column(Float)
    qty = Column(Float)
    ts = Column(DateTime, default=datetime.utcnow)

class Quote(Base):
    __tablename__ = "quotes"
    id = Column(Integer, primary_key=True, index=True)
    bond_id = Column(Integer, ForeignKey("bonds.id"))
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --------- Matching Engine (very simple) ---------
def get_order_book(db, bond_id: int):
    buys = db.query(Order).filter(Order.bond_id==bond_id, Order.side=="buy", Order.status.in_(["open","partial"])).order_by(Order.price.desc(), Order.ts.asc()).all()
    sells = db.query(Order).filter(Order.bond_id==bond_id, Order.side=="sell", Order.status.in_(["open","partial"])).order_by(Order.price.asc(), Order.ts.asc()).all()
    return buys, sells

def match_orders(db, bond_id: int):
    trades_made = []
    while True:
        buys, sells = get_order_book(db, bond_id)
        if not buys or not sells:
            break
        best_buy = buys[0]
        best_sell = sells[0]
        if best_buy.price < best_sell.price:
            break  # no cross
        # execute trade at mid of best prices or sell price (common is maker price). We'll use sell price.
        trade_price = best_sell.price
        remaining_buy = best_buy.qty - best_buy.filled_qty
        remaining_sell = best_sell.qty - best_sell.filled_qty
        qty = min(remaining_buy, remaining_sell)
        # record trade
        trade = Trade(bond_id=bond_id, buy_order_id=best_buy.id, sell_order_id=best_sell.id, price=trade_price, qty=qty)
        db.add(trade)
        trades_made.append(trade)
        # update orders
        best_buy.filled_qty += qty
        best_sell.filled_qty += qty
        best_buy.status = "filled" if best_buy.filled_qty >= best_buy.qty - 1e-9 else "partial"
        best_sell.status = "filled" if best_sell.filled_qty >= best_sell.qty - 1e-9 else "partial"
        db.commit()
    # update quote
    buys, sells = get_order_book(db, bond_id)
    bid = buys[0].price if buys else None
    ask = sells[0].price if sells else None
    q = Quote(bond_id=bond_id, bid=bid, ask=ask)
    db.add(q)
    db.commit()
    return trades_made

# --------- Schemas ---------
class BondIn(BaseModel):
    isin: str
    name: str
    coupon: float
    maturity: str
    face_value: float = 100.0

class OrderIn(BaseModel):
    isin: str
    side: str  # buy or sell
    price: float
    qty: float
    user: Optional[str] = "demo"

# --------- App ---------
app = FastAPI(title="Bond Liquidity Prototype", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# simple WebSocket hub for streaming quotes/trades
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active:
            self.active.remove(websocket)
    async def broadcast(self, message: Dict[str, Any]):
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except WebSocketDisconnect:
                self.disconnect(ws)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/bonds")
def list_bonds():
    with SessionLocal() as db:
        bonds = db.query(Bond).all()
        return [{
            "isin": b.isin, "name": b.name, "coupon": b.coupon, "maturity": b.maturity, "face_value": b.face_value, "id": b.id
        } for b in bonds]

@app.post("/bonds")
def add_bond(bond: BondIn):
    with SessionLocal() as db:
        existing = db.query(Bond).filter(Bond.isin==bond.isin).first()
        if existing:
            raise HTTPException(400, "ISIN already exists")
        b = Bond(**bond.dict())
        db.add(b)
        db.commit()
        return {"status": "ok", "id": b.id}

@app.get("/orderbook/{isin}")
def orderbook(isin: str):
    with SessionLocal() as db:
        bond = db.query(Bond).filter(Bond.isin==isin).first()
        if not bond: raise HTTPException(404, "Bond not found")
        buys, sells = get_order_book(db, bond.id)
        return {
            "isin": isin,
            "bids": [{"id":o.id,"price":o.price,"qty":o.qty,"filled":o.filled_qty,"user":o.user,"ts":o.ts.isoformat()} for o in buys],
            "asks": [{"id":o.id,"price":o.price,"qty":o.qty,"filled":o.filled_qty,"user":o.user,"ts":o.ts.isoformat()} for o in sells],
        }

@app.post("/orders")
async def place_order(order: OrderIn):
    side = order.side.lower()
    if side not in ("buy","sell"):
        raise HTTPException(400, "side must be buy or sell")
    with SessionLocal() as db:
        bond = db.query(Bond).filter(Bond.isin==order.isin).first()
        if not bond: raise HTTPException(404, "Bond not found")
        o = Order(bond_id=bond.id, side=side, price=order.price, qty=order.qty, user=order.user)
        db.add(o)
        db.commit()
        # attempt to match
        trades = match_orders(db, bond.id)
        # broadcast
        payload = {
            "type": "order_update",
            "isin": bond.isin,
            "order_id": o.id,
        }
        await manager.broadcast(payload)
        return {"status":"accepted","order_id":o.id,"trades":[{"id":t.id,"price":t.price,"qty":t.qty} for t in trades]}

@app.get("/trades/{isin}")
def list_trades(isin: str):
    with SessionLocal() as db:
        bond = db.query(Bond).filter(Bond.isin==isin).first()
        if not bond: raise HTTPException(404, "Bond not found")
        trades = db.query(Trade).filter(Trade.bond_id==bond.id).order_by(Trade.ts.desc()).limit(100).all()
        return [{"id":t.id,"price":t.price,"qty":t.qty,"ts":t.ts.isoformat()} for t in trades]

@app.get("/quotes/{isin}")
def latest_quote(isin: str):
    with SessionLocal() as db:
        bond = db.query(Bond).filter(Bond.isin==isin).first()
        if not bond: raise HTTPException(404, "Bond not found")
        q = db.query(Quote).filter(Quote.bond_id==bond.id).order_by(Quote.ts.desc()).first()
        return {"isin": isin, "bid": getattr(q, "bid", None), "ask": getattr(q, "ask", None), "ts": getattr(q, "ts", datetime.utcnow()).isoformat()}

# Seed some demo data
@app.post("/seed")
def seed():
    with SessionLocal() as db:
        if not db.query(Bond).first():
            bonds = [
                Bond(isin="INE123A01011", name="ABC Corp 9.1% 2028", coupon=9.1, maturity="2028-06-30", face_value=1000),
                Bond(isin="INE456B02022", name="XYZ Infra 8.2% 2030", coupon=8.2, maturity="2030-12-31", face_value=1000),
            ]
            db.add_all(bonds)
            db.commit()
        return {"status":"ok"}
