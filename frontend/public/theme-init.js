// Applica il tema prima del primo paint: evita il flash chiaro/scuro.
// File esterno (non inline) per rispettare la CSP `script-src 'self'`.
(function () {
  try {
    var stored = window.localStorage.getItem("mdbup-theme");
    var theme = stored === "light" ? "light" : "dark";
    var root = document.documentElement;
    root.classList.remove("dark", "light");
    root.classList.add(theme);
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
  } catch (error) {
    document.documentElement.classList.add("dark");
  }
})();
