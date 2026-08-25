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

  function syncOAuth() {
    var cb = document.getElementById("field-oauth");
    var grp = document.getElementById("group-oauth");
    if (!cb || !grp) return;
    grp.classList.toggle("hidden", !cb.checked);
  }

  function setupOAuth() {
    var cb = document.getElementById("field-oauth");
    if (!cb || cb.dataset.bound) return;
    cb.dataset.bound = "1";
    cb.addEventListener("change", syncOAuth);
    syncOAuth();
  }

  function setupFormReset() {
    var form = document.getElementById("add-form");
    if (!form || form.dataset.resetBound) return;
    form.dataset.resetBound = "1";
    function doReset() {
      form.reset();
      syncType();
      syncOAuth();
      var headersField = document.getElementById("field-headers");
      if (headersField) headersField.value = "";
      var envField = document.getElementById("field-env");
      if (envField) envField.value = "";
    }
    document.addEventListener("htmx:afterSwap", function (e) {
      var target = e.detail && e.detail.target;
      var xhr = e.detail && e.detail.xhr;
      if (target && target.id === "server-table-body" && xhr && xhr.status === 201) {
        doReset();
      }
    });
    document.addEventListener("htmx:afterRequest", function (e) {
      var xhr = e.detail && e.detail.xhr;
      var target = e.detail && e.detail.target;
      if (xhr && xhr.status === 201 && target && target.id === "server-table-body") {
        doReset();
      }
      if (xhr && xhr.status === 201 && e.target && e.target.id === "add-form") {
        doReset();
      }
    });
    form.addEventListener("htmx:afterRequest", function (e) {
      var xhr = e.detail && e.detail.xhr;
      if (xhr && xhr.status === 201) doReset();
    });
    document.addEventListener("htmx:responseError", function (e) {
      var xhr = e.detail && e.detail.xhr;
      if (xhr && xhr.status >= 400) {
        var toast = document.getElementById("toast");
        if (toast && xhr.responseText && xhr.responseText.indexOf("toast") === -1) {
          var msg = xhr.status + " error";
          try {
            var data = JSON.parse(xhr.responseText);
            if (data.detail) msg = data.detail;
          } catch (_) {}
          var d = document.createElement("div");
          d.className = "bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-xl shadow-sm text-sm";
          d.setAttribute("role", "alert");
          d.textContent = msg;
          toast.innerHTML = "";
          toast.appendChild(d);
          setTimeout(function () { if (toast.contains(d)) toast.removeChild(d); }, 5000);
        }
      }
    });
  }

  function setupVisualFeedback() {
    var form = document.getElementById("add-form");
    if (!form) return;
    function resetButton() {
      var btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = false;
        if (btn.dataset.origText) {
          btn.innerHTML = btn.dataset.origText;
          delete btn.dataset.origText;
        }
      }
    }
    form.addEventListener("submit", function () {
      var btn = form.querySelector('button[type="submit"]');
      if (btn && !btn.disabled) {
        btn.disabled = true;
        btn.dataset.origText = btn.innerHTML;
        btn.innerHTML = '<span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></span> Adding...';
        setTimeout(resetButton, 7000);
      }
    });
    function handleDone(e) {
      resetButton();
    }
    document.addEventListener("htmx:afterSwap", handleDone);
    document.addEventListener("htmx:afterRequest", handleDone);
    document.addEventListener("htmx:afterSettle", handleDone);
    document.addEventListener("htmx:responseError", handleDone);
    document.addEventListener("htmx:sendError", handleDone);
    document.addEventListener("htmx:timeout", handleDone);
    document.addEventListener("htmx:afterSwap", function (e) {
      var xhr = e.detail && e.detail.xhr;
      if (xhr && xhr.status === 201) {
        var isOAuth = document.getElementById("field-oauth") && document.getElementById("field-oauth").checked;
        var toast = document.getElementById("toast");
        if (toast && isOAuth) {
          var d2 = document.createElement("div");
          d2.className = "bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded-xl shadow-sm text-sm flex items-center gap-2";
          d2.setAttribute("role", "status");
          d2.textContent = "OAuth flow started — check browser for authentication";
          toast.appendChild(d2);
          setTimeout(function () { if (toast.contains(d2)) toast.removeChild(d2); }, 6000);
        }
      }
    });
  }

  function init() {
    setupType();
    setupOAuth();
    setupFilter();
    setupCopy();
    setupFormReset();
    setupVisualFeedback();
    syncType();
    syncOAuth();
  }

  document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("htmx:load", init);
  if (document.readyState !== "loading") init();
})();
