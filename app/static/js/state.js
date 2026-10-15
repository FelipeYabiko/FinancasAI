// Shared app state + cached reference data (accounts, categories).
import { get } from "./api.js";
import { currentMonth } from "./fmt.js";

const listeners = new Set();

export const state = {
  user: null,
  month: currentMonth(),
  accounts: [],
  categories: [],
};

export function onChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit(what) {
  listeners.forEach((fn) => fn(what));
}

export async function loadRefs() {
  const [accounts, categories] = await Promise.all([get("/api/accounts"), get("/api/categories")]);
  state.accounts = accounts;
  state.categories = categories;
}

export function categoryById(id) {
  return state.categories.find((c) => c.id === id);
}

export function accountById(id) {
  return state.accounts.find((a) => a.id === id);
}

export function setMonth(month) {
  state.month = month;
  emit("month");
}
