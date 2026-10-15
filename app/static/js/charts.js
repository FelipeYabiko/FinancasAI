// Chart.js helpers that follow the current theme and clean up on re-render.
const live = new Map();

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function themeColors() {
  return {
    text: cssVar("--text"),
    muted: cssVar("--muted"),
    border: cssVar("--border"),
    income: cssVar("--income"),
    expense: cssVar("--expense"),
    primary: cssVar("--primary"),
  };
}

export function chart(canvas, config) {
  if (!window.Chart || !canvas) return null;
  const key = canvas.id;
  live.get(key)?.destroy();
  const c = themeColors();
  window.Chart.defaults.color = c.muted;
  window.Chart.defaults.borderColor = c.border;
  window.Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  const instance = new window.Chart(canvas, {
    ...config,
    options: { responsive: true, maintainAspectRatio: false, ...config.options },
  });
  live.set(key, instance);
  return instance;
}

export function destroyAll() {
  live.forEach((c) => c.destroy());
  live.clear();
}

export const moneyTick = (v) =>
  (v / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
