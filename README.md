
# Backend (FastAPI)

## Setup
```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```
Seed demo data:
```bash
curl -X POST http://localhost:8000/seed
```
Endpoints:
- `GET /bonds`
- `POST /bonds`
- `GET /orderbook/{isin}`
- `POST /orders` (body: `{"isin":"INE123A01011","side":"buy","price":995,"qty":10}`)
- `GET /trades/{isin}`
- `GET /quotes/{isin}`
- WebSocket: `ws://localhost:8000/ws` (broadcasts order updates)
