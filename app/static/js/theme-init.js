// Runs before first paint to avoid a theme flash.
(function () {
  try {
    var t = localStorage.getItem("fia-theme");
    if (t) document.documentElement.dataset.theme = t;
  } catch (e) {}
})();
