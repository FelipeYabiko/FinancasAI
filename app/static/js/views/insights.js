import { html } from "../ui.js";

export async function render(root) {
  root.innerHTML = html`<div class="card empty">Insights chegam em breve.</div>`;
}
