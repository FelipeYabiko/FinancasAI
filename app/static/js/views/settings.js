import { api, del, get, post, put } from "../api.js";
import { ACCOUNT_TYPES, centsToInput, money, parseMoney } from "../fmt.js";
import { categoryById, emit, loadRefs, state } from "../state.js";
import { $, confirmDialog, download, html, modal, toast, toastError } from "../ui.js";
import { applyTheme, currentTheme } from "../theme.js";

// Extra sections registered by later features (AI settings, diagnostics...).
export const extraSections = [];

let tab = "accounts";

const TABS = () => [
  ["accounts", "Contas"],
  ["categories", "Categorias"],
  ["users", "Usuários"],
  ...extraSections.map((s) => [s.id, s.label]),
  ["memory", "Memória de categorias"],
  ["backup", "Backup"],
  ["appearance", "Aparência"],
];

function accountModal(acc, done) {
  const { el, close } = modal(html`<h3>${acc ? "Editar conta" : "Nova conta"}</h3>
    <form id="acc-form" class="grid-form">
      <label class="field" style="grid-column:1/-1">Nome<input name="name" required value="${acc?.name || ""}"></label>
      <label class="field">Tipo<select name="type">${Object.entries(ACCOUNT_TYPES).map(([k, v]) => html`<option value="${k}" ${acc?.type === k ? "selected" : ""}>${v}</option>`)}</select></label>
      <label class="field">Saldo inicial (R$)<input name="initial" inputmode="decimal" value="${acc ? (acc.initial_balance_cents < 0 ? "-" : "") + centsToInput(acc.initial_balance_cents) : "0,00"}"></label>
      <label class="field card-only">Dia de fechamento<input name="closing_day" type="number" min="1" max="31" value="${acc?.closing_day || ""}"></label>
      <label class="field card-only">Dia de vencimento<input name="due_day" type="number" min="1" max="31" value="${acc?.due_day || ""}"></label>
      <label class="field">Cor<input name="color" type="color" value="${acc?.color || "#4f46e5"}"></label>
      <label class="field" style="flex-direction:row;align-items:center;gap:.4rem"><input type="checkbox" name="archived" ${acc?.archived ? html`checked` : ""}> Arquivada</label>
    </form>
    <footer><button class="btn" data-close type="button">Cancelar</button><button class="btn primary" form="acc-form">Salvar</button></footer>`);
  const form = $("#acc-form", el);
  const sync = () => el.querySelectorAll(".card-only").forEach((x) => x.classList.toggle("hidden", form.type.value !== "credit_card"));
  form.type.addEventListener("change", sync);
  sync();
  el.querySelector("[data-close]").addEventListener("click", close);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(form).entries());
    const neg = String(f.initial).trim().startsWith("-");
    const initial = (parseMoney(f.initial) || 0) * (neg ? -1 : 1);
    const body = {
      name: f.name, type: f.type, initial_balance_cents: initial, color: f.color, archived: f.archived === "on",
      closing_day: f.closing_day ? Number(f.closing_day) : null, due_day: f.due_day ? Number(f.due_day) : null,
    };
    try {
      if (acc) await put(`/api/accounts/${acc.id}`, body);
      else await post("/api/accounts", body);
      toast("Conta salva");
      close();
      await loadRefs();
      emit("refs");
      done();
    } catch (err) {
      toastError(err);
    }
  });
}

const sections = {
  async accounts(box, refresh) {
    await loadRefs();
    box.innerHTML = html`<div class="row"><h3 style="margin:0">Contas</h3><span class="spacer"></span><button class="btn primary small" id="new-acc">＋ Nova conta</button></div>
      <ul class="list">${state.accounts.map((a) => html`<li data-id="${a.id}">
        <span><span class="dot" style="background:${a.color}"></span> <b>${a.name}</b> ${a.archived ? html`<span class="badge">arquivada</span>` : ""}
        <br><span class="small muted">${ACCOUNT_TYPES[a.type]}${a.type === "credit_card" ? ` · fecha dia ${a.closing_day}, vence dia ${a.due_day}` : ""}</span></span>
        <span class="row"><b class="num">${money(a.balance_cents)}</b><button class="btn ghost small" data-edit>✏️</button><button class="btn ghost small" data-del>🗑️</button></span></li>`)}</ul>
      ${state.accounts.length ? "" : html`<p class="empty">Cadastre sua primeira conta (ex.: conta corrente, cartão de crédito).</p>`}`;
    $("#new-acc", box).addEventListener("click", () => accountModal(null, refresh));
    box.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => accountModal(state.accounts.find((a) => a.id === Number(b.closest("li").dataset.id)), refresh)));
    box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Excluir conta", "Só é possível excluir contas sem transações. Caso contrário, arquive.", "Excluir", "danger"))) return;
      try {
        await del(`/api/accounts/${b.closest("li").dataset.id}`);
        await loadRefs();
        emit("refs");
        refresh();
      } catch (err) {
        toastError(err);
      }
    }));
  },

  async categories(box, refresh) {
    box.innerHTML = html`<h3>Categorias</h3>
      <form id="cat-form" class="grid-form">
        <label class="field">Nome<input name="name" required></label>
        <label class="field">Tipo<select name="kind"><option value="expense">Despesa</option><option value="income">Receita</option></select></label>
        <label class="field">Ícone<input name="icon" value="🏷️" maxlength="4"></label>
        <label class="field">Cor<input name="color" type="color" value="#64748b"></label>
        <div class="field" style="justify-content:flex-end"><button class="btn primary">Adicionar</button></div>
      </form>
      <div class="table-wrap"><table><tbody>${state.categories.map((c) => html`<tr data-id="${c.id}">
        <td style="width:3.5rem"><input class="inline" data-f="icon" value="${c.icon}" maxlength="4" style="width:3rem" aria-label="Ícone"></td>
        <td><input class="inline" data-f="name" value="${c.name}" aria-label="Nome"></td>
        <td data-hide-sm><span class="badge">${c.kind === "income" ? "receita" : "despesa"}</span></td>
        <td style="width:3.5rem"><input type="color" data-f="color" value="${c.color}" style="padding:0;height:2rem;width:2.5rem" aria-label="Cor"></td>
        <td class="right"><button class="btn ghost small" data-del>🗑️</button></td></tr>`)}</tbody></table></div>`;
    $("#cat-form", box).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await post("/api/categories", Object.fromEntries(new FormData(e.target).entries()));
        await loadRefs();
        refresh();
      } catch (err) {
        toastError(err);
      }
    });
    box.addEventListener("change", async (e) => {
      const f = e.target.dataset.f;
      if (!f) return;
      const c = categoryById(Number(e.target.closest("tr").dataset.id));
      try {
        await put(`/api/categories/${c.id}`, { name: c.name, kind: c.kind, icon: c.icon, color: c.color, [f]: e.target.value });
        await loadRefs();
        toast("Categoria atualizada");
      } catch (err) {
        toastError(err);
      }
    });
    box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Excluir categoria", "As transações dessa categoria ficarão sem categoria.", "Excluir", "danger"))) return;
      await del(`/api/categories/${b.closest("tr").dataset.id}`).catch(toastError);
      await loadRefs();
      refresh();
    }));
  },

  async users(box, refresh) {
    const users = await get("/api/users");
    box.innerHTML = html`<h3>Usuários da família</h3><p class="muted small">Todos compartilham os mesmos dados.</p>
      <ul class="list">${users.map((u) => html`<li data-id="${u.id}"><span><b>${u.name}</b> <span class="muted">@${u.username}</span></span>
        ${u.id === state.user.id ? html`<span class="badge">você</span>` : html`<button class="btn ghost small" data-del>🗑️</button>`}</li>`)}</ul>
      <form id="user-form" class="grid-form" style="margin-top:1rem">
        <label class="field">Nome<input name="name" required></label>
        <label class="field">Usuário<input name="username" required minlength="2" autocomplete="off"></label>
        <label class="field">Senha<input name="password" type="password" required minlength="6" autocomplete="new-password"></label>
        <div class="field" style="justify-content:flex-end"><button class="btn primary">Adicionar usuário</button></div>
      </form>`;
    $("#user-form", box).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await post("/api/users", Object.fromEntries(new FormData(e.target).entries()));
        toast("Usuário criado");
        refresh();
      } catch (err) {
        toastError(err);
      }
    });
    box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Remover usuário", "O usuário perderá o acesso.", "Remover", "danger"))) return;
      await del(`/api/users/${b.closest("li").dataset.id}`).catch(toastError);
      refresh();
    }));
  },

  async memory(box, refresh) {
    const mem = await get("/api/category-memory");
    box.innerHTML = html`<h3>Memória de categorias</h3>
      <p class="muted small">Aprendida quando você corrige categorias. Aplicada antes de chamar a IA (custo zero, determinística).</p>
      ${mem.length ? html`<div class="table-wrap"><table><thead><tr><th>Descrição normalizada</th><th>Categoria</th><th>Usos</th><th></th></tr></thead>
        <tbody>${mem.map((m) => {
          const c = categoryById(m.category_id);
          return html`<tr data-id="${m.id}"><td><code>${m.description_normalized}</code></td><td>${c ? `${c.icon} ${c.name}` : "?"}</td><td>${m.hits}</td>
          <td class="right"><button class="btn ghost small" data-del>🗑️</button></td></tr>`;
        })}</tbody></table></div>` : html`<p class="empty">Ainda vazia.</p>`}`;
    box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      await del(`/api/category-memory/${b.closest("tr").dataset.id}`).catch(toastError);
      refresh();
    }));
  },

  async backup(box) {
    box.innerHTML = html`<h3>Backup</h3>
      <div class="row"><button class="btn" id="exp-json">⬇️ Exportar tudo (JSON)</button><button class="btn" id="exp-csv">⬇️ Exportar transações (CSV)</button></div>
      <h3 style="margin-top:1.5rem">Restaurar</h3>
      <p class="muted small">Substitui <b>todos</b> os dados (contas, categorias, transações, orçamentos, metas, recorrentes) pelo conteúdo do arquivo.</p>
      <div class="row"><input type="file" id="imp-file" accept="application/json,.json" style="max-width:320px"><button class="btn danger" id="imp-json">Restaurar backup</button></div>`;
    $("#exp-json", box).addEventListener("click", () => download("/api/backup/json"));
    $("#exp-csv", box).addEventListener("click", () => download("/api/backup/csv"));
    $("#imp-json", box).addEventListener("click", async () => {
      const file = $("#imp-file", box).files[0];
      if (!file) return toast("Escolha um arquivo .json", "error");
      if (!(await confirmDialog("Restaurar backup", "Todos os dados atuais serão substituídos. Continuar?", "Restaurar", "danger"))) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        const r = await api("/api/backup/json", { method: "POST", body: fd });
        toast(`Backup restaurado: ${r.restored.transactions} transações`);
        await loadRefs();
        emit("data");
      } catch (err) {
        toastError(err);
      }
    });
  },

  async appearance(box) {
    const t = currentTheme();
    box.innerHTML = html`<h3>Aparência</h3>
      <div class="segmented" id="theme-seg">${[["auto", "Automático"], ["light", "Claro"], ["dark", "Escuro"]].map(([k, v]) => html`<button class="btn ${t === k ? "active" : ""}" data-t="${k}">${v}</button>`)}</div>
      <h3 style="margin-top:1.5rem">Atalhos</h3>
      <ul class="list"><li><span>Nova transação</span><span><span class="kbd">Ctrl</span>+<span class="kbd">N</span></span></li>
        <li><span>Importar extrato</span><span><span class="kbd">Ctrl</span>+<span class="kbd">I</span></span></li>
        <li><span>Abrir assistente</span><span><span class="kbd">Ctrl</span>+<span class="kbd">/</span></span></li></ul>`;
    box.querySelectorAll("[data-t]").forEach((b) => b.addEventListener("click", () => {
      applyTheme(b.dataset.t);
      box.querySelectorAll("[data-t]").forEach((x) => x.classList.toggle("active", x === b));
    }));
  },
};

export async function render(root) {
  const tabs = TABS();
  if (!tabs.some(([k]) => k === tab)) tab = "accounts";
  root.innerHTML = html`<div class="card"><div class="segmented" id="settings-tabs" style="flex-wrap:wrap">
      ${tabs.map(([k, v]) => html`<button class="btn ${tab === k ? "active" : ""}" data-tab="${k}">${v}</button>`)}</div></div>
    <div class="card" id="settings-box"></div>`;
  let box = $("#settings-box", root);
  const refresh = async () => {
    const fn = sections[tab] || extraSections.find((s) => s.id === tab)?.render;
    // Fresh element on every refresh so section listeners never stack up.
    const fresh = box.cloneNode(false);
    box.replaceWith(fresh);
    box = fresh;
    try {
      await fn(box, refresh);
    } catch (err) {
      toastError(err);
    }
  };
  root.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
    tab = b.dataset.tab;
    render(root);
  }));
  await refresh();
}

export function openSettingsTab(name) {
  tab = name;
}
