
const API = (path) => `http://localhost:8000${path}`;

async function ping() {
  try {
    const res = await fetch(API("/bonds"));
    const ok = res.ok;
    const el = document.getElementById("backend-status");
    el.textContent = ok ? "online" : "offline";
    el.className = ok ? "ok" : "err";
  } catch(e) {
    const el = document.getElementById("backend-status");
    el.textContent = "offline";
    el.className = "err";
  }
}

async function loadBonds() {
  const ul = document.getElementById("bond-list");
  ul.innerHTML = "";
  const data = await (await fetch(API("/bonds"))).json();
  data.forEach(b => {
    const li = document.createElement("li");
    li.textContent = `${b.isin} — ${b.name} (coupon ${b.coupon}%, FV ₹${b.face_value})`;
    ul.appendChild(li);
  });
}

async function seed() {
  await fetch(API("/seed"), {method:"POST"});
  await loadBonds();
}

async function placeOrder(e) {
  e.preventDefault();
  const body = {
    isin: document.getElementById("isin").value,
    side: document.getElementById("side").value,
    price: parseFloat(document.getElementById("price").value),
    qty: parseFloat(document.getElementById("qty").value),
  };
  const res = await fetch(API("/orders"), {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
  const data = await res.json();
  document.getElementById("result").textContent = JSON.stringify(data, null, 2);
}

async function loadBook() {
  const isin = document.getElementById("book-isin").value;
  const res = await fetch(API(`/orderbook/${isin}`));
  const data = await res.json();
  const bids = document.getElementById("bids");
  const asks = document.getElementById("asks");
  bids.innerHTML = ""; asks.innerHTML = "";
  (data.bids || []).forEach(o => {
    const li = document.createElement("li");
    li.textContent = `${o.price} × ${o.qty - o.filled}`;
    bids.appendChild(li);
  });
  (data.asks || []).forEach(o => {
    const li = document.createElement("li");
    li.textContent = `${o.price} × ${o.qty - o.filled}`;
    asks.appendChild(li);
  });
}

async function loadTrades() {
  const isin = document.getElementById("trades-isin").value;
  const res = await fetch(API(`/trades/${isin}`));
  const data = await res.json();
  const ul = document.getElementById("trades");
  ul.innerHTML = "";
  (data || []).forEach(t => {
    const li = document.createElement("li");
    li.textContent = `${new Date(t.ts).toLocaleTimeString()} — ${t.price} × ${t.qty}`;
    ul.appendChild(li);
  });
}

document.getElementById("order-form").addEventListener("submit", placeOrder);
document.getElementById("seed").addEventListener("click", seed);
document.getElementById("load-book").addEventListener("click", loadBook);
document.getElementById("load-trades").addEventListener("click", loadTrades);

ping();
loadBonds();
