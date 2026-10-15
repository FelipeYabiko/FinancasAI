import { $ } from "./ui.js";

export function init() {
  $("#assistant-close").addEventListener("click", () => toggle(false));
}

export function toggle(force) {
  const panel = $("#assistant-panel");
  const open = force ?? panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  if (open) panel.querySelector("textarea").focus();
}
