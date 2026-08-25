(function () {
  function syncType() {
    var sel = document.getElementById("field-type");
    var urlG = document.getElementById("group-url");
    var cmdG = document.getElementById("group-command");
    if (!sel || !urlG || !cmdG) return;
    var isLocal = sel.value === "local";
    urlG.classList.toggle("hidden", isLocal);
    cmdG.classList.toggle("hidden", !isLocal);
  }

  function setupFilter() {
    var q = document.getElementById("server-filter");
    if (!q) return;
    if (q.dataset.bound) return;
    q.dataset.bound = "1";
    q.addEventListener("input", function () {
      var v = this.value.toLowerCase();
      document.querySelectorAll("tr[data-name]").forEach(function (tr) {
        var name = tr.getAttribute("data-name") || "";
        tr.style.display = name.includes(v) ? "" : "none";
      });
    });
  }

  function setupCopy() {
    if (document.body.dataset.copyBound) return;
    document.body.dataset.copyBound = "1";
    document.addEventListener("click", function (e) {
      var b = e.target.closest(".copy-btn");
      if (!b) return;
      var pre = b.closest("div").nextElementSibling;
      if (pre && navigator.clipboard) {
        navigator.clipboard.writeText(pre.textContent).then(function () {
          var t = b.textContent;
          b.textContent = "Copied!";
          setTimeout(function () {
            b.textContent = t;
          }, 1200);
        });
      }
    });
  }

  function setupType() {
    var sel = document.getElementById("field-type");
    if (!sel || sel.dataset.bound) return;
    sel.dataset.bound = "1";
    sel.addEventListener("change", syncType);
    syncType();
  }

  function init() {
    setupType();
    setupFilter();
    setupCopy();
    syncType();
  }

  document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("htmx:load", init);
  if (document.readyState !== "loading") init();
})();
