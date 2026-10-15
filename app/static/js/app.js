// App bootstrap: auth, hash router, month picker, global search, shortcuts.
import { get, post, setUnauthorizedHandler } from "./api.js";
import { destroyAll } from "./charts.js";
import { openTxForm } from "./components/txForm.js";
import { addMonths, monthLabel } from "./fmt.js";
import { loadRefs, onChange, setMonth, state } from "./state.js";
import { toggleTheme } from "./theme.js";
import { $, $$, toastError } from "./ui.js";
import * as dashboard from "./views/dashboard.js";
import * as transactions from "./views/transactions.js";
import * as budgets from "./views/budgets.js";
import * as goals from "./views/goals.js";
import * as recurring from "./views/recurring.js";
import * as settings from "./views/settings.js";
import * as importView from "./views/import.js";
import * as insights from "./views/insights.js";
import * as assistant from "./assistant.js";

const routes = { dashboard, transactions, budgets, goals, recurring, settings, import: importView, insights };
const MONTHLESS = new Set(["goals", "recurring", "settings", "import"]);

function currentRoute() {
  const name = location.hash.replace(/^#\/?/, "").split("?")[0];
  return routes[name] ? name : "dashboard";
}

let renderSeq = 0;
async function renderView() {
  const name = currentRoute();
  const seq = ++renderSeq;
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  $("#month-picker").style.visibility = MONTHLESS.has(name) ? "hidden" : "visible";
  $("#month-label").textContent = monthLabel(state.month);
  destroyAll();
  const root = $("#view");
  const fresh = root.cloneNode(false); // drop listeners from the previous view
  root.replaceWith(fresh);
  try {
    await routes[name].render(fresh);
  } catch (err) {
    if (seq === renderSeq) {
      fresh.innerHTML = `<div class="card empty">Erro ao carregar: ${err.message}</div>`;
      toastError(err);
    }
  }
}

// ---------- auth ----------
function showAuth(needsSetup) {
  $("#app").classList.add("hidden");
  $("#auth-screen").classList.remove("hidden");
  $("#auth-name-field").classList.toggle("hidden", !needsSetup);
  $("#auth-form").name.required = needsSetup;
  $("#auth-subtitle").textContent = needsSetup
    ? "Primeiro acesso: crie o usuário administrador da família."
    : "Entre para continuar";
  $("#auth-submit").textContent = needsSetup ? "Criar conta e entrar" : "Entrar";
  $("#auth-form").dataset.mode = needsSetup ? "setup" : "login";
  $("#auth-form").username.focus();
}

async function startApp(user) {
  state.user = user;
  $("#whoami").textContent = user.name;
  $("#auth-screen").classList.add("hidden");
  $("#app").classList.remove("hidden");
  await loadRefs();
  if (!location.hash) location.hash = state.accounts.length ? "#/dashboard" : "#/settings";
  await renderView();
}

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target).entries());
  const mode = e.target.dataset.mode;
  $("#auth-error").textContent = "";
  try {
    const user = await post(`/api/auth/${mode}`, mode === "setup" ? f : { username: f.username, password: f.password });
    e.target.reset();
    await startApp(user);
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
});

$("#logout-btn").addEventListener("click", async () => {
  await post("/api/auth/logout").catch(() => {});
  location.hash = "";
  showAuth(false);
});

setUnauthorizedHandler(() => showAuth(false));

// ---------- chrome ----------
$("#month-picker").addEventListener("click", (e) => {
  const step = e.target.closest("[data-step]")?.dataset.step;
  if (step) setMonth(addMonths(state.month, Number(step)));
});

$("#global-search").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  transactions.filters.q = e.target.value.trim();
  transactions.filters.scope = "all";
  e.target.value = "";
  if (currentRoute() === "transactions") renderView();
  else location.hash = "#/transactions";
});

$("#new-tx-btn").addEventListener("click", () => openTxForm());
$("#theme-btn").addEventListener("click", toggleTheme);
$("#assistant-btn").addEventListener("click", () => assistant.toggle());
window.addEventListener("themechange", () => {
  if (currentRoute() === "dashboard" || currentRoute() === "insights") renderView();
});

document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || $("#app").classList.contains("hidden")) return;
  const k = e.key.toLowerCase();
  if (k === "n") {
    e.preventDefault();
    openTxForm();
  } else if (k === "i") {
    e.preventDefault();
    location.hash = "#/import";
  } else if (k === "/") {
    e.preventDefault();
    assistant.toggle(true);
  }
});

window.addEventListener("hashchange", renderView);
onChange((what) => {
  if (what === "month" || what === "data" || what === "refs") renderView();
});

// ---------- boot ----------
(async function boot() {
  assistant.init();
  try {
    const s = await get("/api/auth/status");
    if (s.user) await startApp(s.user);
    else showAuth(s.needs_setup);
  } catch (err) {
    toastError(err);
  }
})();
