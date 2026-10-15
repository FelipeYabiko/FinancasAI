// Statement import: upload PDF → review extracted rows → confirm. History with undo.
import { api, get, post } from "../api.js";
import { accountOptions, categoryOptions } from "../components/options.js";
import { date, money } from "../fmt.js";
import { accountById, emit, setMonth, state } from "../state.js";
import { $, confirmDialog, html, toast, toastError } from "../ui.js";
import { filters as txFilters } from "./transactions.js";

const DOC_TYPES = { checking_statement: "Extrato de conta", credit_card_invoice: "Fatura de cartão", unknown: "Não identificado" };
const STATUS = { pending: "em revisão", committed: "importada", undone: "desfeita", failed: "falhou", discarded: "descartada" };
const DUP = { db: "já existe", near: "parecida com existente", file: "repetida no arquivo" };

let preview = null; // survives navigation while reviewing

function rowHtml(r) {
  const flags = [
    r.duplicate ? html`<span class="badge ${r.duplicate === "file" ? "warn" : "danger"}" title="Possível duplicata">${DUP[r.duplicate]}</span>` : "",
    r.low_confidence ? html`<span class="badge warn" title="Confiança ${Math.round(r.confidence * 100)}%">baixa confiança</span>` : "",
    r.installment_total ? html`<span class="badge">${r.installment_number}/${r.installment_total}</span>` : "",
    r.type === "transfer" ? html`<span class="badge">transferência</span>` : "",
    r.category_source === "memory" ? html`<span class="badge ok" title="Categoria vinda da memória">memória</span>` : r.category_source === "llm" ? html`<span class="badge" title="Categoria sugerida pela IA">IA</span>` : "",
  ];
  return html`<tr data-row="${r.row_id}" class="${r.duplicate && r.duplicate !== "file" ? "row-dup" : ""} ${r.low_confidence ? "row-low" : ""}">
    <td><input type="checkbox" data-f="selected" ${r.selected ? html`checked` : ""} aria-label="Importar linha"></td>
    <td data-hide-sm><input type="date" class="inline" data-f="date" value="${r.date}"></td>
    <td><input class="inline" data-f="description" value="${r.description}" aria-label="Descrição"><div class="small">${flags}</div></td>
    <td data-hide-sm>${r.type === "transfer" ? html`<span class="muted small">—</span>` : html`<select class="inline" data-f="category_id">${categoryOptions(r.category_id, { kind: r.type })}</select>`}</td>
    <td class="right num ${r.amount_cents >= 0 ? "income" : "expense"}"><b>${money(r.amount_cents)}</b><div class="small muted show-sm">${date(r.date)}</div></td>
  </tr>`;
}

function renderReview(root) {
  const p = preview;
  const acc = accountById(p.account_id);
  const selected = p.rows.filter((r) => r.selected);
  const total = selected.reduce((s, r) => s + r.amount_cents, 0);
  root.innerHTML = html`
    <div class="card">
      <div class="row"><h2 style="margin:0">Revisar importação</h2><span class="spacer"></span>
        <button class="btn" id="imp-cancel">Cancelar</button>
        <button class="btn primary" id="imp-commit" ${selected.length ? "" : html`disabled`}>Importar ${selected.length} transações</button></div>
      <p class="small muted" style="margin:.5rem 0 0">
        <b>${p.bank || "Banco não identificado"}</b> · ${DOC_TYPES[p.document_type]} · conta <b>${acc?.name}</b>
        ${p.period_start || p.period_end ? html` · período ${date(p.period_start)} a ${date(p.period_end)}` : ""}
        ${p.invoice_month ? html` · fatura ${p.invoice_month}` : ""}
      </p>
      <p class="small muted" style="margin:.25rem 0 0">${p.rows.length} extraídas · ${p.stats.categorized_from_memory} categorizadas pela memória · ${p.stats.categorized_by_llm} pela IA ·
        ${p.stats.llm_calls} chamadas de IA · US$ ${p.stats.cost_usd.toFixed(5)} · ${(p.stats.latency_ms / 1000).toFixed(1)} s
        · seleção: <b class="num ${total >= 0 ? "income" : "expense"}">${money(total)}</b></p>
      ${p.warnings.length ? html`<ul class="small warning-text" style="margin:.5rem 0 0">${p.warnings.map((w) => html`<li>${w}</li>`)}</ul>` : ""}
      <div class="row small" style="margin-top:.5rem"><button class="btn small" data-sel="all">Marcar todas</button><button class="btn small" data-sel="none">Desmarcar todas</button>
        <button class="btn small" data-sel="nodup">Desmarcar duplicatas</button></div>
    </div>
    <div class="card"><div class="table-wrap"><table class="responsive">
      <thead><tr><th></th><th>Data</th><th>Descrição</th><th>Categoria</th><th class="right">Valor</th></tr></thead>
      <tbody id="imp-body">${p.rows.length ? p.rows.map(rowHtml) : html`<tr><td colspan="5" class="empty">Nenhuma transação encontrada no documento.</td></tr>`}</tbody>
    </table></div></div>`;

  const body = $("#imp-body", root);
  body.addEventListener("change", (e) => {
    const f = e.target.dataset.f;
    if (!f) return;
    const row = p.rows.find((r) => r.row_id === Number(e.target.closest("tr").dataset.row));
    if (f === "selected") row.selected = e.target.checked;
    else if (f === "category_id") row.category_id = e.target.value ? Number(e.target.value) : null;
    else row[f] = e.target.value;
    if (f === "selected") renderReview(root);
  });
  root.querySelectorAll("[data-sel]").forEach((b) => b.addEventListener("click", () => {
    p.rows.forEach((r) => {
      if (b.dataset.sel === "all") r.selected = true;
      else if (b.dataset.sel === "none") r.selected = false;
      else if (r.duplicate && r.duplicate !== "file") r.selected = false;
    });
    renderReview(root);
  }));
  $("#imp-cancel", root).addEventListener("click", async () => {
    await post(`/api/import/${p.batch_id}/discard`).catch(() => {});
    preview = null;
    render(root);
  });
  $("#imp-commit", root).addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const res = await post(`/api/import/${p.batch_id}/commit`, {
        rows: p.rows.map((r) => ({
          date: r.date, description: r.description, amount_cents: r.amount_cents, type: r.type,
          installment_number: r.installment_number, installment_total: r.installment_total,
          category_id: r.category_id, suggested_category_id: r.suggested_category_id, selected: r.selected,
        })),
        invoice_month: acc?.type === "credit_card" ? p.invoice_month : null,
      });
      preview = null;
      toast(`${res.imported} transações importadas${res.skipped ? `, ${res.skipped} ignoradas` : ""}`);
      Object.assign(txFilters, { scope: "month", q: "", category_id: "", account_id: "", type: "", import_batch_id: "" });
      if (res.latest_month) state.month = res.latest_month;
      location.hash = "#/transactions";
      setMonth(state.month);
    } catch (err) {
      e.target.disabled = false;
      toastError(err);
    }
  });
}

async function renderUpload(root) {
  const batches = await get("/api/import/batches");
  root.innerHTML = html`
    <div class="card">
      <h2>Importar extrato ou fatura (PDF)</h2>
      <p class="muted small">O PDF é processado em memória e descartado. Você revisa tudo antes de salvar. PDFs escaneados (imagem) não são suportados.</p>
      <form id="imp-form" class="grid-form">
        <label class="field">Conta de destino<select name="account_id" required>${accountOptions(null)}</select></label>
        <label class="field" style="grid-column:1/-1">
          <div class="dropzone" id="dropzone">📄 Arraste o PDF aqui ou <u>clique para escolher</u><div class="small" id="file-name"></div></div>
          <input type="file" name="file" id="file-input" accept="application/pdf,.pdf" class="hidden" required>
        </label>
        <div class="row" style="grid-column:1/-1"><span class="spacer"></span><button class="btn primary" id="imp-go">Analisar extrato</button></div>
      </form>
      <p id="imp-status" class="small muted"></p>
    </div>
    <div class="card"><h3>Histórico de importações</h3>
      ${batches.length ? html`<div class="table-wrap"><table class="responsive"><thead><tr><th>Quando</th><th>Arquivo</th><th>Banco / tipo</th><th>Resultado</th><th></th></tr></thead><tbody>
        ${batches.map((b) => html`<tr data-id="${b.id}">
          <td class="small">${new Date(b.created_at).toLocaleString("pt-BR")}</td>
          <td>${b.filename}<div class="small muted">${accountById(b.account_id)?.name || ""}</div></td>
          <td data-hide-sm class="small">${b.bank || "—"}<div class="muted">${DOC_TYPES[b.document_type] || ""}</div></td>
          <td class="small"><span class="badge ${b.status === "committed" ? "ok" : b.status === "failed" ? "danger" : ""}">${STATUS[b.status] || b.status}</span>
            ${b.status === "committed" || b.status === "undone" ? html`<div class="muted">${b.imported_count} importadas · ${b.skipped_count} ignoradas</div>` : ""}
            ${b.status === "failed" ? html`<div class="muted">${(b.warnings || [])[0] || ""}</div>` : ""}</td>
          <td class="right">${b.status === "committed" ? html`<button class="btn small" data-view>Ver</button> <button class="btn small danger" data-undo>Desfazer</button>` : ""}</td>
        </tr>`)}</tbody></table></div>` : html`<p class="empty">Nenhuma importação ainda.</p>`}
    </div>`;

  const input = $("#file-input", root);
  const dz = $("#dropzone", root);
  const showName = () => ($("#file-name", root).textContent = input.files[0]?.name || "");
  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", showName);
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("drag");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      showName();
    }
  });
  $("#imp-form", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!input.files[0]) return toast("Escolha um arquivo PDF", "error");
    const fd = new FormData(e.target);
    $("#imp-go", root).disabled = true;
    $("#imp-status", root).textContent = "Lendo o PDF, extraindo e categorizando transações… isso pode levar alguns segundos.";
    try {
      preview = await api("/api/import/preview", { method: "POST", body: fd });
      renderReview(root);
    } catch (err) {
      $("#imp-status", root).textContent = "";
      $("#imp-go", root).disabled = false;
      toastError(err);
    }
  });
  root.querySelectorAll("[data-undo]").forEach((b) => b.addEventListener("click", async () => {
    const id = b.closest("tr").dataset.id;
    if (!(await confirmDialog("Desfazer importação", "Todas as transações desta importação serão excluídas.", "Desfazer", "danger"))) return;
    try {
      const r = await post(`/api/import/${id}/undo`);
      toast(`${r.deleted} transações removidas`);
      emit("data");
    } catch (err) {
      toastError(err);
    }
  }));
  root.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => {
    Object.assign(txFilters, { scope: "all", q: "", category_id: "", account_id: "", type: "", import_batch_id: b.closest("tr").dataset.id });
    location.hash = "#/transactions";
  }));
}

export async function render(root) {
  if (!state.accounts.length) {
    root.innerHTML = html`<div class="card empty">Cadastre uma conta em <a href="#/settings">Configurações</a> antes de importar.</div>`;
    return;
  }
  if (preview) renderReview(root);
  else await renderUpload(root);
}
