(function () {
  const DIALOG_ID = "server-dialog";
  const TOAST_ID = "toast";

  function getDialog() {
    return document.getElementById(DIALOG_ID);
  }
  function getToast() {
    return document.getElementById(TOAST_ID);
  }
  function isEmpty(el) {
    if (!el) return true;
    // robust: childElementCount catches empty aside, textContent trims whitespace-only responses
    if (el.childElementCount === 0) return (el.textContent || "").trim() === "";
    return el.innerHTML.trim() === "";
  }
  function openDialog(d) {
    if (!d || d.open) return;
    try {
      d.showModal();
    } catch (e) {
      console.warn("dialog showModal fallback", e);
      d.setAttribute("open", "");
      d.style.display = "flex";
    }
  }
  function clearDialog(d) {
    if (!d) return;
    if (!isEmpty(d)) d.innerHTML = "";
    // polyfill fallback cleanup: remove open attr/style when not natively open
    if (d.hasAttribute("open") && !d.open) {
      d.removeAttribute("open");
      d.style.display = "none";
    } else if (!d.open) {
      d.style.display = "";
    }
  }
  function showToast(message) {
    var toast = getToast();
    if (!toast) return;
    var el = document.createElement("div");
    el.className = "bg-red-100 border border-red-200 text-red-800 p-3 rounded shadow text-sm";
    el.setAttribute("role", "alert");
    el.textContent = message;
    toast.innerHTML = "";
    toast.appendChild(el);
    setTimeout(function () {
      if (toast.contains(el)) toast.removeChild(el);
    }, 4000);
  }

  function handleDialogError(e, kind) {
    var target = e.detail && e.detail.target;
    if (!target || target.id !== DIALOG_ID) return;
    var xhr = e.detail.xhr;
    var status = xhr ? xhr.status : 0;
    var statusText = xhr ? xhr.statusText : "";
    var response = xhr && xhr.responseText ? xhr.responseText.trim() : "";
    var message;
    if (kind === "timeout") message = "Request timed out — try again";
    else if (kind === "sendError") message = "Network error — check connection";
    else if (status) message = "Error loading details (" + status + (statusText ? " " + statusText : "") + ")";
    else message = "Error loading details";
    showToast(message);
    var dialog = getDialog();
    if (!dialog) return;
    // reuse server-rendered drawer_error HTML if present
    if (response && (response.indexOf("<aside") !== -1 || response.indexOf("Error") !== -1)) {
      dialog.innerHTML = response;
      if (window.htmx) htmx.process(dialog);
    } else {
      // fallback inline error panel; role region avoids nested dialog
      dialog.innerHTML =
        '<aside class="relative w-full max-w-md bg-white shadow-xl h-full overflow-y-auto ml-auto p-6 border-l border-slate-200" role="region" aria-label="Error">' +
        '<div class="flex items-center justify-between mb-4"><h2 class="text-lg font-semibold text-slate-900">Error</h2>' +
        '<button class="rounded-md p-2 text-slate-400 hover:bg-slate-100" aria-label="Close" hx-get="/dashboard/close" hx-target="#' +
        DIALOG_ID +
        '" hx-swap="innerHTML">\u00d7</button></div>' +
        '<div class="bg-red-100 border border-red-200 text-red-800 p-4 rounded">' +
        message.replace(/</g, "&lt;") +
        "</div></aside>";
      if (window.htmx) htmx.process(dialog);
    }
    openDialog(dialog);
  }

  function setupDialog() {
    var dialog = getDialog();
    if (!dialog) return;
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", function () {
      clearDialog(dialog);
    });
    dialog.addEventListener("cancel", function () {
      // 0ms defers to after native cancel handling; 50ms below waits for htmx swap
      setTimeout(function () {
        clearDialog(dialog);
      }, 0);
    });
  }

  function setupHtmxConfig() {
    if (window.htmx && htmx.config) {
      // I1 timeout + indicator: global timeout so offline/500 doesn't hang
      try {
        htmx.config.timeout = 7000;
      } catch (_) {}
    }
  }

  document.addEventListener("htmx:afterSwap", function (e) {
    var target = e.detail.target;
    if (!target || target.id !== DIALOG_ID) return;
    var dialog = getDialog();
    if (!dialog) return;
    if (isEmpty(target)) {
      if (dialog.open) dialog.close();
      // ensure polyfill display reset
      if (dialog.hasAttribute("open") && !dialog.open) {
        dialog.removeAttribute("open");
        dialog.style.display = "none";
      }
      return;
    }
    openDialog(dialog);
  });

  document.addEventListener("htmx:afterSettle", function (e) {
    var target = e.detail.target;
    if (target && target.id === DIALOG_ID && !isEmpty(target)) {
      openDialog(getDialog());
    }
  });

  document.addEventListener("htmx:responseError", function (e) {
    handleDialogError(e, "responseError");
  });
  document.addEventListener("htmx:sendError", function (e) {
    handleDialogError(e, "sendError");
  });
  document.addEventListener("htmx:timeout", function (e) {
    handleDialogError(e, "timeout");
  });
  document.addEventListener("htmx:swapError", function (e) {
    handleDialogError(e, "swapError");
  });

  document.addEventListener("click", function (e) {
    var closeBtn = e.target.closest("#" + DIALOG_ID + ' button[aria-label="Close"]');
    if (closeBtn) {
      var dlg = closeBtn.closest("dialog");
      if (dlg && dlg.open) dlg.close();
    }
  });

  // close via hx-get="/dashboard/close" — wait 50ms for swap to clear before closing
  document.addEventListener("click", function (e) {
    var closeTrigger = e.target.closest('[hx-get="/dashboard/close"]');
    if (closeTrigger) {
      var dialog = getDialog();
      setTimeout(function () {
        if (dialog && dialog.open && isEmpty(dialog)) dialog.close();
        if (dialog && dialog.hasAttribute("open") && isEmpty(dialog)) {
          dialog.removeAttribute("open");
          dialog.style.display = "none";
        }
      }, 50);
    }
  });

  document.addEventListener("htmx:load", function () {
    setupHtmxConfig();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setupDialog();
      setupHtmxConfig();
    });
  } else {
    setupDialog();
    setupHtmxConfig();
  }
})();
