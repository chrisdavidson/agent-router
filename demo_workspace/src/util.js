// demo-shop front-end helpers (demo fixture for agent-router).

export function formatMoney(amount, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}

export function statusBadge(status) {
  const colors = { paid: "green", failed: "red", refunded: "gray" };
  return `<span class="badge badge-${colors[status] ?? "blue"}">${status}</span>`;
}

export function retry(fn, attempts = 3) {
  for (let i = 1; i <= attempts; i++) {
    try {
      return fn();
    } catch (err) {
      if (i === attempts) throw err;
    }
  }
}
