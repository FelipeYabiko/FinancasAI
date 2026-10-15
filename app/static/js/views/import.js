import { html } from "../ui.js";

export async function render(root) {
  root.innerHTML = html`<div class="card empty">Importação de extratos chega na próxima fase.</div>`;
}
