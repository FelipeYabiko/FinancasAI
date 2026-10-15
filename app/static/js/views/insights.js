// Insights: deterministic numbers from the server; optional AI narration on demand.
import { get, post } from "../api.js";
import { date } from "../fmt.js";
import { $, html, toastError } from "../ui.js";

const ICONS = { subscriptions: "🔁", anomaly: "📈", budget: "🎯", forecast: "🔮" };
const BADGE = { info: "", warning: "warn", danger: "danger" };

function detail(item) {
  const d = item.data;
  if (item.kind === "subscriptions") {
    return html`<ul class="list small">${d.items.map((s) => html`<li><span>${s.merchant}</span>
      <span class="num">${s.amount} <span class="muted">· próx. ${date(s.next_expected)}</span></span></li>`)}</ul>`;
  }
  if (item.kind === "forecast") {
    return html`<ul class="list small">
      <li><span>Saldo em contas hoje</span><b class="num">${d.current}</b></li>
      <li><span>Recorrentes a entrar</span><span class="num income">${d.recurring_in}</span></li>
      <li><span>Recorrentes a sair</span><span class="num expense">${d.recurring_out}</span></li>
      <li><span>Outros lançamentos futuros</span><span class="num">${d.scheduled}</span></li>
      <li><span>Faturas a vencer no mês</span><span class="num expense">${d.invoices_due}</span></li>
      <li><span><b>Previsto em ${date(d.end_of_month)}</b></span><b class="num">${d.projected}</b></li></ul>`;
  }
  return "";
}

function renderItems(box, items, meta) {
  box.innerHTML = items.length
    ? html`${items.map((i) => html`<div class="card">
        <div class="row"><span style="font-size:1.3rem">${ICONS[i.kind] || "💡"}</span><b>${i.title}</b><span class="spacer"></span>
          ${i.severity !== "info" ? html`<span class="badge ${BADGE[i.severity]}">${i.severity === "danger" ? "atenção" : "alerta"}</span>` : ""}
          ${i.narrated ? html`<span class="badge" title="Texto escrito pela IA a partir dos números calculados">✨ IA</span>` : ""}</div>
        <p style="margin:.5rem 0">${i.body}</p>${detail(i)}</div>`)}
      ${meta?.error ? html`<p class="small muted" style="grid-column:1/-1">Texto da IA indisponível (${meta.error}); mostrando o texto padrão.</p>` : ""}`.toString()
    : html`<div class="card empty">Ainda não há dados suficientes para insights. Eles aparecem com alguns meses de histórico.</div>`.toString();
}

export async function render(root) {
  root.innerHTML = html`<div class="card"><div class="row"><h2 style="margin:0">Insights</h2><span class="spacer"></span>
      <button class="btn" id="narrate">✨ Escrever com IA</button></div>
      <p class="small muted" style="margin:.4rem 0 0">Assinaturas, gastos fora do padrão, ritmo dos orçamentos e previsão de saldo são calculados de forma determinística. A IA só reescreve o texto a partir desses números.</p></div>
    <div class="grid-2" id="ins-box"><div class="card empty">Calculando…</div></div>`;
  const box = $("#ins-box", root);
  const data = await get("/api/insights");
  renderItems(box, data.items, data.meta);
  $("#narrate", root).addEventListener("click", async (e) => {
    e.target.disabled = true;
    e.target.textContent = "Escrevendo…";
    try {
      const r = await post("/api/insights/narrate");
      renderItems(box, r.items, r.meta);
    } catch (err) {
      toastError(err);
    } finally {
      e.target.disabled = false;
      e.target.textContent = "✨ Escrever com IA";
    }
  });
}
