import { del, get, patch } from "../api.js";
import { openTxForm } from "../components/txForm.js";
import { accountOptions, categoryOptions } from "../components/options.js";
import { date, money, monthLabel, parseMoney, TX_TYPES } from "../fmt.js";
import { accountById, emit, state } from "../state.js";
import { $, $$, choose, confirmDialog, html, toast, toastError } from "../ui.js";

// Filters survive navigation within the session.
export const filters = {
  scope: "month", // month | all
  q: "",
  category_id: "",
  account_id: "",
  type: "",
  min: "",
  max: "",
  date_from: "",
  date_to: "",
  tag: "",
  import_batch_id: "",
};

const PAGE = 200;

function params(offset = 0) {
  const p = {
    q: filters.q,
    account_id: filters.account_id,
    type: filters.type,
    min_cents: parseMoney(filters.min) ?? "",
    max_cents: parseMoney(filters.max) ?? "",
    date_from: filters.date_from,
    date_to: filters.date_to,
    tag: filters.tag,
    import_batch_id: filters.import_batch_id,
    limit: PAGE,
    offset,
  };
  if (filters.category_id === "none") p.uncategorized = true;
  else p.category_id = filters.category_id;
  if (filters.scope === "month") p.month = state.month;
  return p;
}

function rowHtml(tx) {
  const acc = accountById(tx.account_id);
  const isTransfer = tx.type === "transfer";
  const inst = tx.installment_total ? html`<span class="badge">${tx.installment_number}/${tx.installment_total}</span>` : "";
  const origin = tx.origin !== "manual" ? html`<span class="badge" title="origem">${{ import: "importado", assistant: "assistente", recurring: "recorrente" }[tx.origin] || tx.origin}</span>` : "";
  return html`<tr data-id="${tx.id}">
    <td class="num" data-hide-sm>${date(tx.date)}</td>
    <td>
      <input class="inline" data-field="description" value="${tx.description}" aria-label="Descrição">
      <div class="small muted"><span class="show-sm">${date(tx.date)} · </span>${acc?.name || "?"}${tx.invoice_month ? ` · fatura ${tx.invoice_month}` : ""} ${inst} ${origin}
      ${(tx.tags || []).map((t) => html`<span class="badge">#${t}</span>`)}</div>
    </td>
    <td data-hide-sm>${isTransfer ? html`<span class="muted">Transferência</span>`
      : html`<select class="inline" data-field="category_id" aria-label="Categoria">${categoryOptions(tx.category_id, { kind: tx.type })}</select>`}</td>
    <td class="right num ${tx.amount_cents >= 0 ? "income" : "expense"}"><b>${money(tx.amount_cents)}</b></td>
    <td class="right" style="white-space:nowrap">
      <button class="btn ghost small" data-act="edit" title="Editar">✏️</button>
      <button class="btn ghost small" data-act="del" title="Excluir">🗑️</button>
    </td>
  </tr>`;
}

export async function render(root) {
  root.innerHTML = html`
    <div class="card">
      <div class="row" style="margin-bottom:.75rem">
        <h2 style="margin:0">Transações</h2>
        <div class="segmented" id="scope">
          <button class="btn ${filters.scope === "month" ? "active" : ""}" data-scope="month">Este mês</button>
          <button class="btn ${filters.scope === "all" ? "active" : ""}" data-scope="all">Todo o período</button>
        </div>
        <span class="spacer"></span>
        ${filters.import_batch_id ? html`<span class="badge">importação #${filters.import_batch_id}</span>` : ""}
        <button class="btn small" id="clear-filters">Limpar filtros</button>
      </div>
      <form class="filters" id="filters" autocomplete="off">
        <input name="q" placeholder="Texto…" value="${filters.q}">
        <select name="category_id"><option value="">Todas categorias</option><option value="none" ${filters.category_id === "none" ? "selected" : ""}>Sem categoria</option>${categoryOptions(Number(filters.category_id) || null, { empty: null })}</select>
        <select name="account_id">${accountOptions(Number(filters.account_id) || null, { includeArchived: true, empty: "Todas contas" })}</select>
        <select name="type"><option value="">Todos tipos</option>${Object.entries(TX_TYPES).map(([k, v]) => html`<option value="${k}" ${filters.type === k ? "selected" : ""}>${v}</option>`)}</select>
        <input name="min" placeholder="Valor mín." inputmode="decimal" value="${filters.min}">
        <input name="max" placeholder="Valor máx." inputmode="decimal" value="${filters.max}">
        <input name="date_from" type="date" title="De" value="${filters.date_from}">
        <input name="date_to" type="date" title="Até" value="${filters.date_to}">
        <input name="tag" placeholder="Tag" value="${filters.tag}">
      </form>
    </div>
    <div class="cards" id="tx-stats"></div>
    <div class="card"><div class="table-wrap"><table class="responsive">
      <thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th class="right">Valor</th><th></th></tr></thead>
      <tbody id="tx-body"><tr><td colspan="5" class="empty">Carregando…</td></tr></tbody>
    </table></div><div id="tx-more" class="row" style="justify-content:center;margin-top:.5rem"></div></div>`;

  let items = [];
  let total = 0;

  async function load(append = false) {
    try {
      const page = await get("/api/transactions", params(append ? items.length : 0));
      items = append ? items.concat(page.items) : page.items;
      total = page.total;
      const s = page.stats;
      const scopeLabel = filters.scope === "month" ? monthLabel(state.month) : "todo o período";
      $("#tx-stats", root).innerHTML = html`
        <div class="card stat"><div class="label">Transações · ${scopeLabel}</div><div class="value num">${s.count}</div></div>
        <div class="card stat"><div class="label">Receitas</div><div class="value num income">${money(s.income_cents)}</div></div>
        <div class="card stat"><div class="label">Despesas</div><div class="value num expense">${money(s.expense_cents)}</div></div>
        <div class="card stat"><div class="label">Saldo</div><div class="value num ${s.net_cents >= 0 ? "income" : "expense"}">${money(s.net_cents)}</div></div>`;
      $("#tx-body", root).innerHTML = items.length
        ? items.map(rowHtml).join("")
        : html`<tr><td colspan="5" class="empty">Nenhuma transação encontrada.</td></tr>`;
      $("#tx-more", root).innerHTML = items.length < total
        ? html`<button class="btn" id="load-more">Carregar mais (${items.length}/${total})</button>`
        : "";
      $("#load-more", root)?.addEventListener("click", () => load(true));
    } catch (err) {
      toastError(err);
    }
  }

  let debounce;
  $("#filters", root).addEventListener("input", (e) => {
    filters[e.target.name] = e.target.value;
    clearTimeout(debounce);
    debounce = setTimeout(() => load(), 250);
  });
  $("#filters", root).addEventListener("submit", (e) => e.preventDefault());
  $$("#scope button", root).forEach((b) =>
    b.addEventListener("click", () => {
      filters.scope = b.dataset.scope;
      $$("#scope button", root).forEach((x) => x.classList.toggle("active", x === b));
      load();
    }),
  );
  $("#clear-filters", root).addEventListener("click", () => {
    Object.assign(filters, { q: "", category_id: "", account_id: "", type: "", min: "", max: "", date_from: "", date_to: "", tag: "", import_batch_id: "" });
    render(root);
  });

  const body = $("#tx-body", root);
  body.addEventListener("change", async (e) => {
    const el = e.target.closest("[data-field]");
    if (!el) return;
    const id = Number(el.closest("tr").dataset.id);
    const value = el.dataset.field === "category_id" ? (el.value ? Number(el.value) : null) : el.value.trim();
    if (el.dataset.field === "description" && !value) return;
    try {
      await patch(`/api/transactions/${id}`, { [el.dataset.field]: value });
      toast(el.dataset.field === "category_id" ? "Categoria atualizada (memorizada para próximas importações)" : "Descrição atualizada");
    } catch (err) {
      toastError(err);
      load();
    }
  });
  body.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches("input.inline")) e.target.blur();
  });
  body.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const id = Number(btn.closest("tr").dataset.id);
    const tx = items.find((t) => t.id === id);
    if (btn.dataset.act === "edit") return openTxForm(tx);
    try {
      if (tx.installment_group_id) {
        const v = await choose("Excluir parcela", `"${tx.description}" faz parte de um parcelamento em ${tx.installment_total}x.`, [
          { value: "one", label: "Só esta parcela" },
          { value: "all", label: "Todas as parcelas", kind: "danger" },
        ]);
        if (!v) return;
        const r = await del(`/api/transactions/${id}`, { whole_group: v === "all" });
        toast(`${r.deleted} transação(ões) excluída(s)`);
      } else {
        const msg = tx.transfer_pair_id ? "Os dois lados da transferência serão excluídos." : `Excluir "${tx.description}"?`;
        if (!(await confirmDialog("Excluir transação", msg, "Excluir", "danger"))) return;
        await del(`/api/transactions/${id}`);
        toast("Transação excluída");
      }
      emit("data");
    } catch (err) {
      toastError(err);
    }
  });

  await load();
}
