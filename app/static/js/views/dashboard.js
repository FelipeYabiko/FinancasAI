import { get } from "../api.js";
import { chart, moneyTick, themeColors } from "../charts.js";
import { date, money, monthLabel, monthShortLabel, pct } from "../fmt.js";
import { state } from "../state.js";
import { html } from "../ui.js";

function deltaClass(v, goodWhenUp) {
  if (v === null || v === undefined) return "muted";
  return (v >= 0) === goodWhenUp ? "income" : "expense";
}

export async function render(root) {
  const d = await get("/api/dashboard", { month: state.month });
  const hasData = d.last_6_months.some((m) => m.income_cents || m.expense_cents);
  root.innerHTML = html`
    <div class="cards">
      <div class="card stat"><div class="label">Saldo total</div>
        <div class="value num ${d.total_balance_cents < 0 ? "expense" : ""}">${money(d.total_balance_cents)}</div>
        <div class="delta muted">${d.accounts.length} conta(s)</div></div>
      <div class="card stat"><div class="label">Receitas · ${monthLabel(d.month)}</div>
        <div class="value num income">${money(d.income_cents)}</div>
        <div class="delta ${deltaClass(d.income_change_pct, true)}">${pct(d.income_change_pct)} vs mês anterior</div></div>
      <div class="card stat"><div class="label">Despesas · ${monthLabel(d.month)}</div>
        <div class="value num expense">${money(d.expense_cents)}</div>
        <div class="delta ${deltaClass(d.expense_change_pct, false)}">${pct(d.expense_change_pct)} vs mês anterior</div></div>
      <div class="card stat"><div class="label">Resultado do mês</div>
        <div class="value num ${d.net_cents >= 0 ? "income" : "expense"}">${money(d.net_cents)}</div>
        <div class="delta muted">receitas − despesas (sem transferências)</div></div>
    </div>

    <div class="grid-2">
      <div class="card"><h3>Saldo por conta</h3>
        ${d.accounts.length ? html`<ul class="list">${d.accounts.map((a) => html`
          <li><span><span class="dot" style="background:${a.color}"></span> ${a.name}</span>
          <b class="num ${a.balance_cents < 0 ? "expense" : ""}">${money(a.balance_cents)}</b></li>`)}</ul>`
          : html`<p class="empty">Nenhuma conta. <a href="#/settings">Cadastre uma conta</a>.</p>`}
      </div>
      <div class="card"><h3>Faturas em aberto</h3>
        ${d.open_invoices.length ? html`<ul class="list">${d.open_invoices.slice(0, 6).map((i) => html`
          <li><span>${i.account_name} · <span class="muted">fatura ${monthShortLabel(i.invoice_month)}</span><br>
          <span class="small muted">vence ${date(i.due_date)}</span></span>
          <b class="num expense">${money(i.amount_cents)}</b></li>`)}</ul>`
          : html`<p class="empty">Nenhuma fatura em aberto.</p>`}
      </div>
    </div>

    <div class="grid-2">
      <div class="card"><h3>Receitas × despesas (6 meses)</h3><div class="chart-box"><canvas id="ch-months"></canvas></div></div>
      <div class="card"><h3>Gastos por categoria</h3>
        ${d.by_category.length ? html`<div class="chart-box"><canvas id="ch-cats"></canvas></div>` : html`<p class="empty">Sem despesas no mês.</p>`}
      </div>
    </div>

    <div class="grid-2">
      <div class="card"><h3>Orçamentos do mês</h3>
        ${d.budgets.length ? html`<ul class="list">${d.budgets.map((b) => {
          const c = state.categories.find((x) => x.id === b.category_id);
          return html`<li style="flex-direction:column;gap:.3rem"><div class="row"><span>${c ? `${c.icon} ${c.name}` : "?"}</span><span class="spacer"></span>
            <span class="num small">${money(b.spent_cents)} / ${money(b.limit_cents)}</span>
            ${b.status !== "ok" ? html`<span class="badge ${b.status === "exceeded" ? "danger" : "warn"}">${b.status === "exceeded" ? "estourou" : "80%+"}</span>` : ""}</div>
            <div class="progress ${b.status}"><span style="width:${Math.min(b.percent, 100)}%"></span></div></li>`;
        })}</ul>` : html`<p class="empty">Sem orçamentos. <a href="#/budgets">Criar orçamento</a>.</p>`}
      </div>
      <div class="card"><h3>Top estabelecimentos</h3>
        ${d.top_merchants.length ? html`<ul class="list">${d.top_merchants.map((m) => html`
          <li><span style="text-transform:capitalize">${m.name} <span class="muted small">(${m.count}x)</span></span><b class="num">${money(m.amount_cents)}</b></li>`)}</ul>`
          : html`<p class="empty">Sem despesas no mês.</p>`}
      </div>
    </div>
    <div class="card"><h3>Gastos por dia da semana</h3><div class="chart-box" style="height:200px"><canvas id="ch-week"></canvas></div></div>
    ${hasData ? "" : html`<p class="muted small">Dica: use <span class="kbd">Ctrl</span>+<span class="kbd">N</span> para lançar, <span class="kbd">Ctrl</span>+<span class="kbd">I</span> para importar um extrato e <span class="kbd">Ctrl</span>+<span class="kbd">/</span> para falar com o assistente.</p>`}
  `;

  const c = themeColors();
  chart(root.querySelector("#ch-months"), {
    type: "bar",
    data: {
      labels: d.last_6_months.map((m) => monthShortLabel(m.month)),
      datasets: [
        { label: "Receitas", data: d.last_6_months.map((m) => m.income_cents), backgroundColor: c.income },
        { label: "Despesas", data: d.last_6_months.map((m) => m.expense_cents), backgroundColor: c.expense },
      ],
    },
    options: {
      scales: { y: { ticks: { callback: moneyTick } } },
      plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${money(ctx.raw)}` } } },
    },
  });
  if (d.by_category.length) {
    chart(root.querySelector("#ch-cats"), {
      type: "doughnut",
      data: {
        labels: d.by_category.map((x) => `${x.icon} ${x.name}`),
        datasets: [{ data: d.by_category.map((x) => x.amount_cents), backgroundColor: d.by_category.map((x) => x.color), borderWidth: 0 }],
      },
      options: {
        plugins: {
          legend: { position: "right" },
          tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${money(ctx.raw)}` } },
        },
      },
    });
  }
  chart(root.querySelector("#ch-week"), {
    type: "bar",
    data: {
      labels: d.by_weekday.map((w) => w.weekday),
      datasets: [{ label: "Despesas", data: d.by_weekday.map((w) => w.amount_cents), backgroundColor: c.primary }],
    },
    options: {
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => money(ctx.raw) } } },
      scales: { y: { ticks: { callback: moneyTick } } },
    },
  });
}
