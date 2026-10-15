// "Nova transação" / "Editar transação" modal with expense, income, installment and transfer modes.
import { patch, post } from "../api.js";
import { centsToInput, parseMoney, todayISO } from "../fmt.js";
import { emit, state } from "../state.js";
import { $, html, modal, toast, toastError } from "../ui.js";
import { accountOptions, categoryOptions } from "./options.js";

const MODES = [
  ["expense", "Despesa"],
  ["income", "Receita"],
  ["installments", "Parcelada"],
  ["transfer", "Transferência"],
];

function fields(mode, tx) {
  const d = tx?.date || todayISO();
  const amount = tx ? centsToInput(tx.amount_cents) : "";
  if (mode === "transfer") {
    return html`
      <label class="field">Data<input type="date" name="date" value="${d}" required></label>
      <label class="field">Valor (R$)<input name="amount" inputmode="decimal" value="${amount}" placeholder="0,00" required></label>
      <label class="field">De<select name="from_account_id" required>${accountOptions(null)}</select></label>
      <label class="field">Para<select name="to_account_id" required>${accountOptions(state.accounts[1]?.id)}</select></label>
      <label class="field" style="grid-column:1/-1">Descrição<input name="description" value="Transferência"></label>`;
  }
  const kind = mode === "income" ? "income" : "expense";
  return html`
    <label class="field">Data${mode === "installments" ? " da compra" : ""}<input type="date" name="date" value="${d}" required></label>
    <label class="field">${mode === "installments" ? "Valor total (R$)" : "Valor (R$)"}<input name="amount" inputmode="decimal" value="${amount}" placeholder="0,00" required></label>
    ${mode === "installments" ? html`<label class="field">Parcelas<input type="number" name="installments" min="2" max="72" value="2" required></label>` : ""}
    <label class="field" style="grid-column:1/-1">Descrição<input name="description" value="${tx?.description || ""}" required maxlength="200"></label>
    <label class="field">Conta<select name="account_id" required>${accountOptions(tx?.account_id ?? (mode === "installments" ? state.accounts.find((a) => a.type === "credit_card")?.id : null))}</select></label>
    <label class="field">Categoria<select name="category_id">${categoryOptions(tx?.category_id ?? null, { kind })}</select></label>
    <label class="field">Tags (vírgula)<input name="tags" value="${(tx?.tags || []).join(", ")}"></label>
    ${mode === "expense" ? html`<label class="field" style="flex-direction:row;align-items:center;gap:.4rem"><input type="checkbox" name="is_refund" ${tx && tx.type === "expense" && tx.amount_cents > 0 ? html`checked` : ""}> Estorno / reembolso</label>` : ""}
    ${mode !== "installments" ? html`<label class="field" style="grid-column:1/-1">Notas<input name="notes" value="${tx?.notes || ""}"></label>` : ""}`;
}

export function openTxForm(tx = null) {
  if (!state.accounts.length) {
    toast("Cadastre uma conta em Configurações primeiro.", "error");
    location.hash = "#/settings";
    return;
  }
  let mode = tx ? tx.type : "expense";
  const editing = Boolean(tx);
  const { el, close } = modal(
    html`<h3>${editing ? "Editar transação" : "Nova transação"}</h3>
      ${editing ? "" : html`<div class="segmented" id="tx-modes">${MODES.map(([m, l]) => html`<button type="button" class="btn ${m === mode ? "active" : ""}" data-mode="${m}">${l}</button>`)}</div>`}
      <form id="tx-form" class="grid-form"></form>
      <p class="error" id="tx-error"></p>
      <footer>
        <button class="btn" type="button" data-close>Cancelar</button>
        <button class="btn primary" type="submit" form="tx-form">Salvar</button>
      </footer>`,
  );
  const form = $("#tx-form", el);
  const renderFields = () => {
    form.innerHTML = fields(mode, tx).toString();
  };
  renderFields();
  el.querySelector("[data-close]").addEventListener("click", close);
  el.querySelectorAll("[data-mode]").forEach((b) =>
    b.addEventListener("click", () => {
      mode = b.dataset.mode;
      el.querySelectorAll("[data-mode]").forEach((x) => x.classList.toggle("active", x === b));
      renderFields();
    }),
  );
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form).entries());
    const cents = parseMoney(f.amount);
    if (!cents) {
      $("#tx-error", el).textContent = "Valor inválido";
      return;
    }
    const tags = (f.tags || "").split(",").map((t) => t.trim()).filter(Boolean);
    const category_id = f.category_id ? Number(f.category_id) : null;
    try {
      if (editing) {
        await patch(`/api/transactions/${tx.id}`, tx.type === "transfer"
          ? { date: f.date, description: f.description, notes: f.notes || "" }
          : {
              date: f.date, description: f.description, amount_cents: cents, account_id: Number(f.account_id),
              category_id, tags, notes: f.notes || "", is_refund: f.is_refund === "on",
            });
        toast("Transação atualizada");
      } else if (mode === "transfer") {
        await post("/api/transactions/transfers", {
          date: f.date, amount_cents: cents, description: f.description || "Transferência",
          from_account_id: Number(f.from_account_id), to_account_id: Number(f.to_account_id),
        });
        toast("Transferência criada");
      } else if (mode === "installments") {
        const r = await post("/api/transactions/installments", {
          date: f.date, description: f.description, total_cents: cents, installments: Number(f.installments),
          account_id: Number(f.account_id), category_id, tags,
        });
        toast(`${r.length} parcelas criadas`);
      } else {
        await post("/api/transactions", {
          date: f.date, description: f.description, amount_cents: cents, type: mode,
          account_id: Number(f.account_id), category_id, tags, notes: f.notes || "", is_refund: f.is_refund === "on",
        });
        toast("Transação criada");
      }
      close();
      emit("data");
    } catch (err) {
      $("#tx-error", el).textContent = err.message;
      toastError(err);
    }
  });
}
