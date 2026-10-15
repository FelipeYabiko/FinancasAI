// Minimal UI kit: html templating, modals, confirm dialogs, toasts.
import { escapeHtml } from "./fmt.js";

/** Tagged template that escapes interpolations unless wrapped with raw(). */
export function html(strings, ...values) {
  let out = "";
  strings.forEach((s, i) => {
    out += s;
    if (i < values.length) out += render(values[i]);
  });
  return new Raw(out);
}

class Raw {
  constructor(s) {
    this.s = s;
  }
  toString() {
    return this.s;
  }
}

export const raw = (s) => new Raw(s);

function render(v) {
  if (v === null || v === undefined || v === false) return "";
  if (v instanceof Raw) return v.s;
  if (Array.isArray(v)) return v.map(render).join("");
  return escapeHtml(v);
}

export function $(sel, root = document) {
  return root.querySelector(sel);
}
export function $$(sel, root = document) {
  return [...root.querySelectorAll(sel)];
}

export function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "error" ? 6000 : 3500);
}

export function toastError(err) {
  toast(err?.message || String(err), "error");
}

/**
 * Open a modal. `content` is an html`` result. Returns {el, close}.
 * `onMount(el, close)` lets callers wire events.
 */
export function modal(content, { wide = false, onMount, onClose } = {}) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">${content}</div>`;
  const el = backdrop.firstElementChild;
  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
    onClose?.();
  };
  const onKey = (e) => {
    if (e.key === "Escape") close();
  };
  backdrop.addEventListener("mousedown", (e) => {
    if (e.target === backdrop) close();
  });
  document.addEventListener("keydown", onKey);
  $("#modal-root").appendChild(backdrop);
  onMount?.(el, close);
  const first = el.querySelector("input:not([type=hidden]), select, textarea, button.primary");
  first?.focus();
  return { el, close };
}

/** Promise-based confirmation dialog. Resolves to the chosen option value or null. */
export function choose(title, message, options) {
  return new Promise((resolve) => {
    let chosen = null;
    modal(
      html`<h3>${title}</h3><p>${message}</p>
        <footer>
          <button class="btn" data-v="__cancel">Cancelar</button>
          ${options.map((o) => html`<button class="btn ${o.kind || ""}" data-v="${o.value}">${o.label}</button>`)}
        </footer>`,
      {
        onMount(el, close) {
          el.querySelectorAll("button[data-v]").forEach((b) =>
            b.addEventListener("click", () => {
              chosen = b.dataset.v === "__cancel" ? null : b.dataset.v;
              close();
            }),
          );
        },
        onClose: () => resolve(chosen),
      },
    );
  });
}

export async function confirmDialog(title, message, label = "Confirmar", kind = "primary") {
  return (await choose(title, message, [{ value: "yes", label, kind }])) === "yes";
}

export function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

export function download(url) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
