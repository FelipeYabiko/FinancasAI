// Settings sections: AI provider/model per feature + "Diagnóstico de IA".
import { get, post, put } from "../api.js";
import { chart, themeColors } from "../charts.js";
import { $, html, toast, toastError } from "../ui.js";
import { extraSections } from "./settings.js";

const FEATURE_LABELS = {
  extraction: "Extração de extratos (PDF)",
  categorization: "Categorização",
  assistant: "Assistente",
  insights: "Texto dos insights",
};

const usd = (v) => `US$ ${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 6 })}`;

async function renderSettings(box, refresh) {
  const s = await get("/api/ai/settings");
  const providers = Object.keys(s.providers);
  box.innerHTML = html`<h3>Provedor e modelo de IA</h3>
    <p class="muted small">Cada funcionalidade usa seu próprio provedor/modelo. Chaves de API ficam só no servidor (<code>.env</code>).
      Provedores sem chave: ${providers.filter((p) => !s.providers[p]).join(", ") || "nenhum"}.</p>
    <datalist id="model-list">${s.models.map((m) => html`<option value="${m.model}">${m.provider} · $${m.input}/$${m.output} por 1M</option>`)}</datalist>
    <form id="ai-form">
      <div class="table-wrap"><table><thead><tr><th>Funcionalidade</th><th>Provedor</th><th>Modelo</th><th>Prompt</th><th></th></tr></thead><tbody>
      ${Object.entries(s.features).map(([f, cfg]) => html`<tr data-f="${f}">
        <td><b>${FEATURE_LABELS[f] || f}</b></td>
        <td><select name="${f}.provider">${providers.map((p) => html`<option value="${p}" ${p === cfg.provider ? "selected" : ""}>${p}${s.providers[p] ? "" : " (sem chave)"}</option>`)}</select></td>
        <td><input name="${f}.model" value="${cfg.model}" list="model-list" required></td>
        <td class="small muted">${f}.${s.prompt_versions[f]?.default || "-"}</td>
        <td><button class="btn small" type="button" data-test="${f}">Testar</button></td></tr>`)}
      </tbody></table></div>
      <div class="row" style="margin-top:.75rem"><span class="spacer"></span><button class="btn primary">Salvar</button></div>
    </form>
    <p class="small" id="ai-test-out"></p>`;
  $("#ai-form", box).addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const body = {};
    for (const f of Object.keys(s.features)) body[f] = { provider: fd[`${f}.provider`], model: fd[`${f}.model`] };
    try {
      await put("/api/ai/settings", body);
      toast("Configuração de IA salva");
      refresh();
    } catch (err) {
      toastError(err);
    }
  });
  box.querySelectorAll("[data-test]").forEach((b) => b.addEventListener("click", async () => {
    const out = $("#ai-test-out", box);
    out.textContent = "Testando…";
    try {
      const r = await post(`/api/ai/test/${b.dataset.test}`);
      out.innerHTML = r.ok
        ? html`<span class="income">✔ ${r.provider}/${r.model} respondeu “${r.reply}” em ${r.latency_ms} ms · ${r.input_tokens}+${r.output_tokens} tokens · ${usd(r.cost_usd)}</span>`.toString()
        : html`<span class="expense">✖ ${r.provider}/${r.model}: ${r.error}</span>`.toString();
    } catch (err) {
      out.textContent = err.message;
    }
  }));
}

async function renderDiagnostics(box) {
  const d = await get("/api/ai/diagnostics", { days: 30 });
  box.innerHTML = html`<h3>Diagnóstico de IA · últimos ${d.days} dias</h3>
    <div class="cards">
      <div class="card stat"><div class="label">Custo total</div><div class="value num">${usd(d.total_cost_usd)}</div></div>
      <div class="card stat"><div class="label">Chamadas</div><div class="value num">${d.total_calls}</div></div>
      <div class="card stat"><div class="label">Latência p50 / p95</div><div class="value num">${d.p50_ms} / ${d.p95_ms} ms</div></div>
      <div class="card stat"><div class="label">Taxa de erro</div><div class="value num ${d.error_rate > 5 ? "expense" : ""}">${d.error_rate}%</div></div>
    </div>
    <h3 style="margin-top:1rem">Por funcionalidade</h3>
    ${d.by_feature.length ? html`<div class="table-wrap"><table><thead><tr><th>Feature</th><th class="right">Chamadas</th><th class="right">Tokens (in/out)</th><th class="right">Custo</th><th class="right">p50</th><th class="right">p95</th><th class="right">Erros</th></tr></thead>
      <tbody>${d.by_feature.map((f) => html`<tr><td>${f.feature}</td><td class="right num">${f.calls}</td><td class="right num">${f.input_tokens.toLocaleString("pt-BR")} / ${f.output_tokens.toLocaleString("pt-BR")}</td>
      <td class="right num">${usd(f.cost_usd)}</td><td class="right num">${f.p50_ms} ms</td><td class="right num">${f.p95_ms} ms</td><td class="right num">${f.errors}</td></tr>`)}</tbody></table></div>` : html`<p class="empty">Nenhuma chamada ainda.</p>`}
    <h3 style="margin-top:1rem">Chamadas por dia</h3>
    <div class="chart-box" style="height:200px"><canvas id="ch-ai-days"></canvas></div>
    <h3 style="margin-top:1rem">Últimas falhas</h3>
    ${d.recent_failures.length ? html`<ul class="list">${d.recent_failures.map((f) => html`<li style="flex-direction:column;gap:.1rem">
      <span><span class="badge danger">${f.status}</span> <b>${f.feature}</b> · ${f.provider}/${f.model} · <span class="muted small">${f.prompt_version} · ${new Date(f.created_at).toLocaleString("pt-BR")}</span></span>
      <span class="small muted" style="word-break:break-word">${f.error_message || ""}</span></li>`)}</ul>` : html`<p class="empty">Sem falhas 🎉</p>`}
    <h3 style="margin-top:1rem">Chamadas recentes</h3>
    ${d.recent_calls.length ? html`<div class="table-wrap"><table><thead><tr><th>Quando</th><th>Feature</th><th>Modelo</th><th>Prompt</th><th class="right">Tokens</th><th class="right">Custo</th><th class="right">Latência</th><th>Status</th></tr></thead><tbody>
      ${d.recent_calls.map((c) => html`<tr><td class="small">${new Date(c.created_at).toLocaleString("pt-BR")}</td><td>${c.feature}</td><td class="small">${c.provider}/${c.model}</td><td class="small">${c.prompt_version}</td>
      <td class="right num">${c.input_tokens}+${c.output_tokens}</td><td class="right num">${usd(c.cost_usd)}</td><td class="right num">${c.latency_ms} ms</td>
      <td><span class="badge ${c.status === "ok" ? "ok" : "danger"}">${c.status}</span></td></tr>`)}</tbody></table></div>` : ""}`;
  const c = themeColors();
  chart($("#ch-ai-days", box), {
    type: "bar",
    data: {
      labels: d.per_day.map((x) => x.day.slice(5).split("-").reverse().join("/")),
      datasets: [
        { label: "OK", data: d.per_day.map((x) => x.calls - x.errors), backgroundColor: c.primary, stack: "s" },
        { label: "Erros", data: d.per_day.map((x) => x.errors), backgroundColor: c.expense, stack: "s" },
      ],
    },
    options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { precision: 0 } } } },
  });
}

extraSections.push({ id: "ai", label: "IA", render: renderSettings });
extraSections.push({ id: "ai-diagnostics", label: "Diagnóstico de IA", render: renderDiagnostics });
