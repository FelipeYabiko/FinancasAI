import { del, get, patch, post } from "../api.js";
import { date, money, parseMoney } from "../fmt.js";
import { $, confirmDialog, html, toast, toastError } from "../ui.js";

export async function render(root) {
  const goals = await get("/api/goals");
  root.innerHTML = html`
    <div class="card"><h2>Metas</h2>
      <form id="goal-form" class="grid-form">
        <label class="field">Nome<input name="name" required placeholder="Ex.: Reserva de emergência"></label>
        <label class="field">Valor alvo (R$)<input name="target" inputmode="decimal" required></label>
        <label class="field">Já guardado (R$)<input name="current" inputmode="decimal" placeholder="0,00"></label>
        <label class="field">Prazo<input name="deadline" type="date"></label>
        <div class="field" style="justify-content:flex-end"><button class="btn primary">Criar meta</button></div>
      </form>
    </div>
    <div class="cards">
      ${goals.length ? goals.map((g) => html`<div class="card" data-id="${g.id}">
        <div class="row"><b>${g.name}</b><span class="spacer"></span><span class="badge ${g.percent >= 100 ? "ok" : ""}">${g.percent}%</span></div>
        <div class="progress" style="margin:.6rem 0"><span style="width:${g.percent}%"></span></div>
        <div class="small"><span class="num">${money(g.current_cents)}</span> de <span class="num">${money(g.target_cents)}</span>
          ${g.deadline ? html`<span class="muted"> · até ${date(g.deadline)}</span>` : ""}</div>
        <form class="row" data-add style="margin-top:.6rem">
          <input name="amount" inputmode="decimal" placeholder="Valor" style="flex:1" aria-label="Valor">
          <button class="btn small" name="op" value="add">+ Adicionar</button>
          <button class="btn small" name="op" value="sub">− Retirar</button>
          <button class="btn small" name="op" value="set" title="Definir valor atual">=</button>
        </form>
        <div class="row" style="margin-top:.4rem"><span class="spacer"></span><button class="btn ghost small" data-del>🗑️ Excluir</button></div>
      </div>`) : html`<div class="card empty">Nenhuma meta ainda.</div>`}
    </div>`;

  $("#goal-form", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    const target = parseMoney(f.target);
    if (!target) return toast("Valor alvo inválido", "error");
    try {
      await post("/api/goals", { name: f.name, target_cents: target, current_cents: parseMoney(f.current) || 0, deadline: f.deadline || null });
      toast("Meta criada");
      render(root);
    } catch (err) {
      toastError(err);
    }
  });
  root.querySelectorAll("form[data-add]").forEach((form) =>
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = Number(form.closest("[data-id]").dataset.id);
      const g = goals.find((x) => x.id === id);
      const amount = parseMoney(form.amount.value);
      if (amount === null) return toast("Valor inválido", "error");
      const op = e.submitter?.value || "add";
      const current = op === "set" ? amount : Math.max(0, g.current_cents + (op === "add" ? amount : -amount));
      try {
        await patch(`/api/goals/${id}`, { current_cents: current });
        toast(`Meta atualizada: ${money(current)}`);
        render(root);
      } catch (err) {
        toastError(err);
      }
    }),
  );
  root.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      const id = b.closest("[data-id]").dataset.id;
      if (!(await confirmDialog("Excluir meta", "Tem certeza?", "Excluir", "danger"))) return;
      await del(`/api/goals/${id}`).catch(toastError);
      render(root);
    }),
  );
}
