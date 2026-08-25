(function () {
  function getDialog() {
    return document.getElementById("server-dialog");
  }
  function isEmpty(el) {
    return !el || el.innerHTML.trim() === "";
  }
  function setupDialog() {
    var dialog = getDialog();
    if (!dialog) return;
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) {
        dialog.close();
      }
    });
    dialog.addEventListener("close", function () {
      if (!isEmpty(dialog)) {
        dialog.innerHTML = "";
      }
    });
    dialog.addEventListener("cancel", function () {
      if (!isEmpty(dialog)) {
        setTimeout(function () {
          dialog.innerHTML = "";
        }, 0);
      }
    });
  }
  function setupStopPropagation() {
    document.querySelectorAll('tr[hx-get] button').forEach(function (btn) {
      if (btn.dataset.stopBound) return;
      btn.dataset.stopBound = "1";
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
      });
    });
    document.querySelectorAll("#server-dialog button[aria-label='Close']").forEach(function (btn) {
      if (btn.dataset.closeBound) return;
      btn.dataset.closeBound = "1";
      btn.addEventListener("click", function () {
        var dlg = btn.closest("dialog");
        if (dlg && dlg.open) {
          dlg.close();
        }
      });
    });
  }
  document.addEventListener("htmx:afterSwap", function (e) {
    var target = e.detail.target;
    if (!target || target.id !== "server-dialog") return;
    var dialog = getDialog();
    if (!dialog) return;
    var empty = isEmpty(target);
    if (empty) {
      if (dialog.open) dialog.close();
      return;
    }
    if (!dialog.open) {
      try {
        dialog.showModal();
      } catch (_) {
        dialog.setAttribute("open", "");
        dialog.style.display = "flex";
      }
    }
    setupStopPropagation();
  });
  document.addEventListener("htmx:afterSettle", function (e) {
    var target = e.detail.target;
    if (target && target.id === "server-dialog" && !isEmpty(target)) {
      var dialog = getDialog();
      if (dialog && !dialog.open) {
        try {
          dialog.showModal();
        } catch (_) {}
      }
    }
  });
  document.addEventListener("htmx:load", function () {
    setupStopPropagation();
  });
  document.addEventListener("click", function (e) {
    var closeBtn = e.target.closest('[hx-get="/dashboard/close"]');
    if (closeBtn) {
      var dialog = getDialog();
      setTimeout(function () {
        if (dialog && dialog.open && isEmpty(dialog)) {
          dialog.close();
        }
      }, 50);
    }
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setupDialog();
      setupStopPropagation();
    });
  } else {
    setupDialog();
    setupStopPropagation();
  }
})();
