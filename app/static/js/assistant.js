// Side-panel assistant: chat + confirmation cards for every write the model proposes.
import { post } from "./api.js";
import { emit } from "./state.js";
import { $, html, toastError } from "./ui.js";

const TOOL_LABELS = {
  query_transactions: "buscou transações",
  get_summary: "consultou o resumo",
  create_transaction: "preparou um lançamento",
  create_installment_purchase: "preparou uma compra parcelada",
  create_transfer: "preparou uma transferência",
  set_budget: "preparou um orçamento",
  create_goal: "preparou uma meta",
  update_goal: "preparou a atualização de meta",
  delete_transaction: "preparou uma exclusão",
};

let conversationId = null;
let busy = false;

function add(role, content) {
  const box = $("#assistant-messages");
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = String(content);
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  return el;
}

function actionCard(a) {
  const el = add("assistant", html`<b>Confirmar ação?</b><div class="preview">${a.summary}</div><div class="actions"><button class="btn primary small" data-ok>Confirmar</button><button class="btn small" data-no>Cancelar</button></div>`);
  const decide = async (decision) => {
    el.querySelectorAll("button").forEach((b) => (b.disabled = true));
    try {
      const r = await post(`/api/assistant/actions/${a.id}/${decision}`);
      const ok = r.status === "confirmed";
      el.querySelector(".actions").innerHTML = html`<span class="small ${ok ? "income" : r.status === "failed" ? "expense" : "muted"}">${
        ok ? "✔ Feito" : r.status === "cancelled" ? "Cancelado" : `✖ Falhou: ${r.result?.error || ""}`
      }</span>`.toString();
      if (ok) emit("data");
    } catch (err) {
      el.querySelectorAll("button").forEach((b) => (b.disabled = false));
      toastError(err);
    }
  };
  el.querySelector("[data-ok]").addEventListener("click", () => decide("confirm"));
  el.querySelector("[data-no]").addEventListener("click", () => decide("cancel"));
}

async function send(message) {
  if (busy) return;
  busy = true;
  add("user", html`${message}`);
  const thinking = add("system", "pensando…");
  try {
    const r = await post("/api/assistant/chat", { message, conversation_id: conversationId });
    conversationId = r.conversation_id;
    thinking.remove();
    const tools = [...new Set(r.steps.filter((s) => !s.pending_action_id).map((s) => TOOL_LABELS[s.tool] || s.tool))];
    if (tools.length) add("system", html`🔧 ${tools.join(", ")}`);
    if (r.reply) add("assistant", html`${r.reply}`);
    r.pending_actions.forEach(actionCard);
  } catch (err) {
    thinking.remove();
    add("system", html`⚠️ ${err.message}`);
  } finally {
    busy = false;
  }
}

function greet() {
  $("#assistant-messages").innerHTML = "";
  add("assistant", html`Olá! Posso lançar gastos, responder sobre suas finanças e organizar orçamentos e metas. Exemplos: <i>“gastei 45 no mercado ontem no Nubank”</i>, <i>“quanto gastei com delivery esse mês?”</i>, <i>“comprei uma TV de 3 mil em 10x no cartão”</i>. Sempre peço sua confirmação antes de alterar qualquer coisa.`);
}

export function init() {
  greet();
  $("#assistant-close").addEventListener("click", () => toggle(false));
  $("#assistant-reset").addEventListener("click", () => {
    conversationId = null;
    greet();
  });
  const form = $("#assistant-form");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const msg = form.message.value.trim();
    if (!msg) return;
    form.message.value = "";
    send(msg);
  });
  form.message.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
}

export function toggle(force) {
  const panel = $("#assistant-panel");
  const open = force ?? panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  if (open) panel.querySelector("textarea").focus();
}
