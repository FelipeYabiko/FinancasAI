import { del, get, post, put } from "../api.js";
import { accountOptions, categoryOptions } from "../components/options.js";
import { centsToInput, currentMonth, money, parseMoney } from "../fmt.js";
import { accountById, categoryById, emit } from "../state.js";
import { $, confirmDialog, html, modal, toast, toastError } from "../ui.js";

function ruleForm(rule) {
  return html`<form id="rule-form" class="grid-form">
    <label class="field" style="grid-column:1/-1">Descrição<input name="description" required value="${rule?.description || ""}"></label>
    <label class="field">Tipo<select name="type">
      <option value="expense" ${rule?.type !== "income" ? "selected" : ""}>Despesa</option>
      <option value="income" ${rule?.type === "income" ? "selected" : ""}>Receita</option></select></label>
    <label class="field">Valor (R$)<input name="amount" inputmode="decimal" required value="${rule ? centsToInput(rule.amount_cents) : ""}"></label>
    <label class="field">Dia do mês<input name="day_of_month" type="number" min="1" max="31" required value="${rule?.day_of_month || 5}"></label>
    <label class="field">A partir de<input name="start_month" type="month" required value="${rule?.start_month || currentMonth()}"></label>
    <label class="field">Conta<select name="account_id" required>${accountOptions(rule?.account_id ?? null)}</select></label>
    <label class="field">Categoria<select name="category_id">${categoryOptions(rule?.category_id ?? null)}</select></label>
    <label class="field" style="flex-direction:row;align-items:center;gap:.4rem"><input type="checkbox" name="active" ${!rule || rule.active ? html`checked` : ""}> Ativa</label>
  </form>`;
}

function openRuleModal(rule, onSaved) {
  const { el, close } = modal(html`<h3>${rule ? "Editar recorrência" : "Nova recorrência"}</h3>${ruleForm(rule)}
    <p class="muted small">A transação é lançada automaticamente quando o mês chega, sem duplicar.</p>
    <footer><button class="btn" data-close type="button">Cancelar</button><button class="btn primary" form="rule-form">Salvar</button></footer>`);
  el.querySelector("[data-close]").addEventListener("click", close);
  $("#rule-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    const cents = parseMoney(f.amount);
    if (!cents) return toast("Valor inválido", "error");
    const body = {
      description: f.description, type: f.type, amount_cents: cents, day_of_month: Number(f.day_of_month),
      start_month: f.start_month, account_id: Number(f.account_id), category_id: f.category_id ? Number(f.category_id) : null,
      active: f.active === "on",
    };
    try {
      if (rule) await put(`/api/recurring/${rule.id}`, body);
      else await post("/api/recurring", body);
      toast("Recorrência salva");
      close();
      emit("data");
      onSaved();
    } catch (err) {
      toastError(err);
    }
  });
}

export async function render(root) {
  const rules = await get("/api/recurring");
  root.innerHTML = html`
    <div class="card"><div class="row"><h2 style="margin:0">Recorrentes</h2><span class="spacer"></span>
      <button class="btn primary" id="new-rule">＋ Nova recorrência</button></div></div>
    <div class="card"><div class="table-wrap"><table class="responsive">
      <thead><tr><th>Descrição</th><th>Dia</th><th>Conta / categoria</th><th class="right">Valor</th><th></th></tr></thead>
      <tbody>${rules.length ? rules.map((r) => {
        const c = categoryById(r.category_id);
        return html`<tr data-id="${r.id}" style="${r.active ? "" : "opacity:.55"}">
          <td><b>${r.description}</b> ${r.active ? "" : html`<span class="badge">inativa</span>`}<div class="small muted">desde ${r.start_month}</div></td>
          <td data-hide-sm>dia ${r.day_of_month}</td>
          <td data-hide-sm>${accountById(r.account_id)?.name || "?"}<div class="small muted">${c ? `${c.icon} ${c.name}` : "Sem categoria"}</div></td>
          <td class="right num ${r.type === "income" ? "income" : "expense"}">${money(r.type === "income" ? r.amount_cents : -r.amount_cents)}</td>
          <td class="right" style="white-space:nowrap"><button class="btn ghost small" data-edit>✏️</button><button class="btn ghost small" data-del>🗑️</button></td>
        </tr>`;
      }) : html`<tr><td colspan="5" class="empty">Nenhuma recorrência (ex.: aluguel, salário, streaming).</td></tr>`}</tbody>
    </table></div></div>`;
  const refresh = () => render(root);
  $("#new-rule", root).addEventListener("click", () => openRuleModal(null, refresh));
  root.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => openRuleModal(rules.find((r) => r.id === Number(b.closest("tr").dataset.id)), refresh)),
  );
  root.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!(await confirmDialog("Excluir recorrência", "Transações já lançadas serão mantidas.", "Excluir", "danger"))) return;
      await del(`/api/recurring/${b.closest("tr").dataset.id}`).catch(toastError);
      refresh();
    }),
  );
}
