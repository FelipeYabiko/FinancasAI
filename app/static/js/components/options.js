import { html } from "../ui.js";
import { state } from "../state.js";

export function accountOptions(selected, { includeArchived = false, empty = null } = {}) {
  const accs = state.accounts.filter((a) => includeArchived || !a.archived || a.id === selected);
  return html`${empty !== null ? html`<option value="">${empty}</option>` : ""}${accs.map(
    (a) => html`<option value="${a.id}" ${a.id === selected ? html`selected` : ""}>${a.name}</option>`,
  )}`;
}

export function categoryOptions(selected, { kind = null, empty = "Sem categoria" } = {}) {
  const cats = state.categories.filter((c) => !kind || c.kind === kind || c.id === selected);
  return html`${empty !== null ? html`<option value="">${empty}</option>` : ""}${cats.map(
    (c) => html`<option value="${c.id}" ${c.id === selected ? html`selected` : ""}>${c.icon} ${c.name}</option>`,
  )}`;
}
