export function currentTheme() {
  try {
    return localStorage.getItem("fia-theme") || "auto";
  } catch (_) {
    return "auto";
  }
}

export function applyTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  try {
    if (t === "auto") localStorage.removeItem("fia-theme");
    else localStorage.setItem("fia-theme", t);
  } catch (_) {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event("themechange"));
}

export function toggleTheme() {
  const dark = document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  applyTheme(dark ? "light" : "dark");
}
