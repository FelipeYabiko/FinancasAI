// Formatting helpers. Money is always integer cents.

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function money(cents) {
  // Integer math -> string, then Intl just for grouping/symbol.
  return brl.format(cents / 100);
}

export function signedMoney(cents) {
  return (cents > 0 ? "+" : "") + money(cents);
}

/** Parse user input like "1.234,56", "45", "45.9", "R$ 10,00" into positive cents. */
export function parseMoney(text) {
  if (text === null || text === undefined) return null;
  let s = String(text).trim().replace(/R\$\s?/i, "").replace(/\s/g, "");
  if (!s) return null;
  s = s.replace(/^-/, "");
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  else if ((s.match(/\./g) || []).length > 1) s = s.replace(/\./g, "");
  if (!/^\d+(\.\d{0,2})?$/.test(s)) return null;
  const [int, dec = ""] = s.split(".");
  return parseInt(int, 10) * 100 + parseInt((dec + "00").slice(0, 2), 10);
}

/** cents -> "1234,56" for input fields. */
export function centsToInput(cents) {
  const abs = Math.abs(cents);
  return `${Math.floor(abs / 100)},${String(abs % 100).padStart(2, "0")}`;
}

export function date(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

const monthFmt = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" });
const monthShort = new Intl.DateTimeFormat("pt-BR", { month: "short", timeZone: "UTC" });

export function monthLabel(month) {
  const [y, m] = month.split("-").map(Number);
  const s = monthFmt.format(new Date(Date.UTC(y, m - 1, 1)));
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function monthShortLabel(month) {
  const [y, m] = month.split("-").map(Number);
  return monthShort.format(new Date(Date.UTC(y, m - 1, 1))).replace(".", "") + "/" + String(y).slice(2);
}

export function todayISO() {
  // Local date in America/Sao_Paulo
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
}

export function currentMonth() {
  return todayISO().slice(0, 7);
}

export function addMonths(month, n) {
  const [y, m] = month.split("-").map(Number);
  const idx = y * 12 + (m - 1) + n;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

export function pct(v) {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${v.toLocaleString("pt-BR")}%`;
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export const ACCOUNT_TYPES = {
  checking: "Conta corrente",
  credit_card: "Cartão de crédito",
  cash: "Dinheiro",
  savings: "Poupança/Investimento",
};

export const TX_TYPES = { income: "Receita", expense: "Despesa", transfer: "Transferência" };
