import { del, get, post, put } from "../api.js";
import { categoryOptions } from "../components/options.js";
import { addMonths, centsToInput, money, monthLabel, parseMoney } from "../fmt.js";
import { categoryById, state } from "../state.js";
import { $, confirmDialog, html, toast, toastError } from "../ui.js";

export async function render(root) {
  const budgets = await get("/api/budgets", { month: state.month });
  const totalLimit = budgets.reduce((s, b) => s + b.limit_cents, 0);
  const totalSpent = budgets.reduce((s, b) => s + b.spent_cents, 0);
  root.innerHTML = html`
    <div class="card">
      <div class="row"><h2 style="margin:0">Orçamentos · ${monthLabel(state.month)}</h2><span class="spacer"></span>
        <button class="btn small" id="copy-prev">Copiar do mês anterior</button></div>
      <p class="muted small">Alerta em 80% e ao estourar 100% do limite.</p>
      <form id="budget-form" class="grid-form">
        <label class="field">Categoria<select name="category_id" required>${categoryOptions(null, { kind: "expense", empty: null })}</select></label>
        <label class="field">Limite (R$)<input name="limit" inputmode="decimal" required placeholder="0,00"></label>
        <div class="field" style="justify-content:flex-end"><button class="btn primary" type="submit">Definir orçamento</button></div>
      </form>
    </div>
    ${budgets.length ? html`<div class="card"><div class="row"><b>Total</b><span class="spacer"></span><span class="num">${money(totalSpent)} / ${money(totalLimit)}</span></div></div>` : ""}
    <div class="cards">
      ${budgets.length ? budgets.map((b) => {
        const c = categoryById(b.category_id);
        const left = b.limit_cents - b.spent_cents;
        return html`<div class="card" data-id="${b.id}" data-cat="${b.category_id}">
          <div class="row"><b>${c ? `${c.icon} ${c.name}` : "?"}</b><span class="spacer"></span>
            ${b.status === "exceeded" ? html`<span class="badge danger">estourou</span>` : b.status === "warning" ? html`<span class="badge warn">atenção</span>` : html`<span class="badge ok">ok</span>`}</div>
          <div class="progress ${b.status}" style="margin:.6rem 0"><span style="width:${Math.min(b.percent, 100)}%"></span></div>
          <div class="row small"><span class="num">${money(b.spent_cents)} de</span>
            <input class="inline num" data-limit value="${centsToInput(b.limit_cents)}" style="width:7rem" inputmode="decimal" aria-label="Limite">
            <span class="spacer"></span><span class="muted">${b.percent}%</span></div>
          <div class="row small" style="margin-top:.4rem"><span class="${left < 0 ? "expense" : "muted"}">${left < 0 ? `${money(-left)} acima` : `${money(left)} disponível`}</span>
            <span class="spacer"></span><button class="btn ghost small" data-del>🗑️</button></div>
        </div>`;
      }) : html`<div class="card empty">Nenhum orçamento para este mês.</div>`}
    </div>`;

  $("#budget-form", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    const cents = parseMoney(f.limit);
    if (!cents) return toast("Limite inválido", "error");
    try {
      await put("/api/budgets", { category_id: Number(f.category_id), month: state.month, limit_cents: cents });
      toast("Orçamento salvo");
      render(root);
    } catch (err) {
      toastError(err);
    }
  });
  $("#copy-prev", root).addEventListener("click", async () => {
    try {
      const r = await post("/api/budgets/copy", undefined, { from_month: addMonths(state.month, -1), to_month: state.month });
      toast(`${r.copied} orçamento(s) copiado(s)`);
      render(root);
    } catch (err) {
      toastError(err);
    }
  });
  root.addEventListener("change", async (e) => {
    if (!e.target.matches("[data-limit]")) return;
    const card = e.target.closest("[data-id]");
    const cents = parseMoney(e.target.value);
    if (!cents) return toast("Limite inválido", "error");
    try {
      await put("/api/budgets", { category_id: Number(card.dataset.cat), month: state.month, limit_cents: cents });
      render(root);
    } catch (err) {
      toastError(err);
    }
  });
  root.addEventListener("click", async (e) => {
    if (!e.target.closest("[data-del]")) return;
    const card = e.target.closest("[data-id]");
    if (!(await confirmDialog("Excluir orçamento", "Remover este orçamento do mês?", "Excluir", "danger"))) return;
    try {
      await del(`/api/budgets/${card.dataset.id}`);
      render(root);
    } catch (err) {
      toastError(err);
    }
  });
}
