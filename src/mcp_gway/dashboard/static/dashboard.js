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

  function setupGlobalErrorToast(){
    if(document.body.dataset.globalErrorBound) return;
    document.body.dataset.globalErrorBound="1";
    document.addEventListener("htmx:responseError", function(e){
      var xhr=e.detail && e.detail.xhr;
      var target=e.detail && e.detail.target;
      // if already has toast OOB, skip
      if(xhr && xhr.responseText && xhr.responseText.indexOf("hx-swap-oob")!==-1) return;
      if(xhr && xhr.responseText && xhr.responseText.indexOf("toast")!==-1) return;
      if(!xhr || !xhr.status) return;
      var toast=document.getElementById("toast");
      if(!toast) return;
      var msg="Request failed ("+xhr.status+")";
      try{
        var data=JSON.parse(xhr.responseText);
        if(data.detail) msg=data.detail;
        else if(data.message) msg=data.message;
      }catch(_){
        if(xhr.responseText && xhr.responseText.length<300) msg=xhr.responseText.trim().replace(/<[^>]*>/g,"").slice(0,200);
      }
      // also try to extract from drawer feedback if present
      var drawerFb=document.getElementById("drawer-feedback");
      if(target && (target.id==="drawer-feedback" || target.id==="drawer-reveal-output") && xhr.responseText){
        // already swapped via handleSwap, dont duplicate
        return;
      }
      var d=document.createElement("div");
      d.className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-xl shadow-sm text-sm";
      d.setAttribute("role","alert");
      d.textContent=msg;
      toast.appendChild(d);
      setTimeout(function(){ if(toast.contains(d)) toast.removeChild(d); }, 5000);
    });
    document.addEventListener("htmx:sendError", function(e){
      var toast=document.getElementById("toast");
      if(!toast) return;
      var d=document.createElement("div");
      d.className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-xl shadow-sm text-sm";
      d.setAttribute("role","alert");
      d.textContent="Network error — check connection";
      toast.appendChild(d);
      setTimeout(function(){ if(toast.contains(d)) toast.removeChild(d); }, 5000);
    });
  }

  function setupRevealVisibility(){
    document.addEventListener("htmx:afterSwap", function(e){
      var t=e.detail && e.detail.target;
      if(t && t.id==="drawer-reveal-output"){
        t.style.display="block";
        t.classList.remove("hidden");
        var fresh=document.getElementById("drawer-reveal-output");
        if(fresh){
          fresh.style.display="block";
          fresh.classList.remove("hidden");
          fresh.scrollIntoView({behavior:"smooth", block:"nearest"});
        }
      }
      if(t && t.id==="drawer-feedback"){
        t.scrollIntoView({behavior:"smooth", block:"nearest"});
      }
    });
  }

  function setupRevealToggle(){
    if(document.body.dataset.revealToggleBound) return;
    document.body.dataset.revealToggleBound="1";
    document.addEventListener('click', function(e){
      var btn = e.target.closest('#reveal-btn, .reveal-toggle-btn');
      if(!btn) return;
      // only handle reveal buttons inside drawer
      if(!btn.closest('aside')) return;
      e.preventDefault();
      e.stopPropagation();
      window.toggleReveal(btn);
    });
  }

  window.toggleReveal = function(btn){
    var out = document.getElementById('drawer-reveal-output');
    var spinner = document.getElementById('reveal-spinner');
    if(!out || !btn) return;
    var isVisible = out && !out.classList.contains('hidden') && out.style.display !== 'none' && out.innerHTML.trim() !== '' && out.textContent.trim() !== '';
    // if output has emerald background (revealed), consider visible
    if(isVisible && out.innerHTML.trim() !== '' && out.textContent.indexOf('No secrets') === -1){
      out.classList.add('hidden');
      out.style.display='none';
      out.innerHTML='';
      btn.textContent='Reveal';
      btn.setAttribute('aria-label','Reveal secrets');
      return;
    }
    var url = btn.getAttribute('data-reveal-url');
    if(!url) return;
    if(spinner) { spinner.classList.remove('hidden'); spinner.style.display='inline-flex'; }
    btn.disabled = true;
    var prevText = btn.textContent;
    btn.textContent = 'Revealing…';
    fetch(url, {method:'POST', headers:{'HX-Request':'true'}})
      .then(function(r){ return r.text().then(function(t){ return {status:r.status, text:t, headers:r.headers}; }); })
      .then(function(res){
        var temp = document.createElement('template');
        temp.innerHTML = res.text.trim();
        var newOut = temp.content.querySelector('#drawer-reveal-output');
        var toastFrag = temp.content.querySelector('#toast');
        if(newOut){
          out.outerHTML = newOut.outerHTML;
          var fresh = document.getElementById('drawer-reveal-output');
          if(fresh){
            fresh.classList.remove('hidden');
            fresh.style.display='block';
            fresh.scrollIntoView({behavior:'smooth', block:'nearest'});
          }
          btn.textContent='Hide';
          btn.setAttribute('aria-label','Hide secrets');
          if(toastFrag){
            var toast=document.getElementById('toast');
            if(toast){
              toast.innerHTML = toastFrag.innerHTML;
              setTimeout(function(){ if(toast) toast.innerHTML=''; }, 4000);
            }
          }
        } else {
          // fallback: handle non-HTML (e.g., JSON) or error
          if(res.status===200){
            out.innerHTML = res.text;
            out.classList.remove('hidden');
            out.style.display='block';
            btn.textContent='Hide';
          } else {
            var toast2=document.getElementById('toast');
            if(toast2){
              var d=document.createElement('div');
              d.className='bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-xl shadow-sm text-sm';
              d.textContent='Reveal failed ('+res.status+')';
              toast2.appendChild(d);
              setTimeout(function(){ if(toast2.contains(d)) toast2.removeChild(d); }, 4000);
            }
            btn.textContent='Reveal';
          }
        }
      })
      .catch(function(){
        var toast=document.getElementById('toast');
        if(toast){
          var d=document.createElement('div');
          d.className='bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-xl shadow-sm text-sm';
          d.textContent='Failed to reveal';
          toast.appendChild(d);
          setTimeout(function(){ if(toast.contains(d)) toast.removeChild(d); }, 4000);
        }
        btn.textContent='Reveal';
      })
      .finally(function(){
        btn.disabled=false;
        if(spinner){ spinner.classList.add('hidden'); spinner.style.display='none'; }
        if(btn.textContent==='Revealing…') btn.textContent='Reveal';
      });
  };

  function setupToastAutoHide(){
    var toast=document.getElementById('toast');
    if(!toast) return;
    if(toast.dataset.autoHideBound) return;
    toast.dataset.autoHideBound="1";
    var hideTimer=null;
    function scheduleHide(){
      if(hideTimer) clearTimeout(hideTimer);
      if(!toast.innerHTML.trim()) return;
      hideTimer=setTimeout(function(){
        if(toast) toast.innerHTML='';
        hideTimer=null;
      }, 4500);
    }
    // htmx OOB and direct innerHTML
    var observer=new MutationObserver(function(){ scheduleHide(); });
    observer.observe(toast, {childList:true, subtree:true, characterData:true});
    document.addEventListener('htmx:afterSwap', function(e){
      if(e.detail && e.detail.target && e.detail.target.id==='toast') scheduleHide();
      if(e.detail && e.detail.target && e.detail.target.id==='drawer-feedback') {
        // also ensure toast from OOB gets hidden
        if(toast.innerHTML.trim()) scheduleHide();
      }
    });
    document.addEventListener('htmx:oobAfterSwap', function(e){
      if(e.detail && e.detail.target && e.detail.target.id==='toast') scheduleHide();
    });
    // initial if already has content
    if(toast.innerHTML.trim()) scheduleHide();
  }

  function setupHeaderToast(){
    if(document.body.dataset.headerToastBound) return;
    document.body.dataset.headerToastBound="1";
    document.addEventListener("htmx:afterRequest", function(e){
      var xhr = e.detail && e.detail.xhr;
      if(!xhr) return;
      var toastMsg = null;
      var oauthRequired = null;
      try{ toastMsg = xhr.getResponseHeader('X-Toast'); }catch(_){}
      try{ oauthRequired = xhr.getResponseHeader('X-OAuth-Required'); }catch(_){}
      if(toastMsg){
        var toastEl=document.getElementById('toast');
        if(toastEl){
          var d=document.createElement('div');
          var isOAuth = oauthRequired === '1' || toastMsg.indexOf('OAuth') !== -1;
          d.className=isOAuth ? 'bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded-xl shadow-sm text-sm flex items-center gap-2' : 'bg-amber-50 border border-amber-200 text-amber-900 px-4 py-3 rounded-xl shadow-sm text-sm';
          d.setAttribute('role', isOAuth ? 'status' : 'alert');
          d.textContent=toastMsg;
          toastEl.appendChild(d);
          setTimeout(function(){ if(toastEl.contains(d)) toastEl.removeChild(d); }, isOAuth ? 8000 : 4500);
        }
      }
      if(oauthRequired === '1'){
        var serverName = null;
        try{
          var form=document.getElementById('add-form');
          if(form){
            var inp=form.querySelector('#field-name');
            if(inp) serverName=inp.value;
          }
        }catch(_){}
        if(serverName){
          (function(name){
            var toastEl3=document.getElementById('toast');
            function showOAuthToast(msg, isError){
              if(!toastEl3) return;
              var d3=document.createElement('div');
              d3.className= isError ? 'bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-xl shadow-sm text-sm' : 'bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded-xl shadow-sm text-sm flex items-center gap-2';
              d3.setAttribute('role', isError ? 'alert' : 'status');
              d3.textContent=msg;
              toastEl3.appendChild(d3);
              setTimeout(function(){ if(toastEl3.contains(d3)) toastEl3.removeChild(d3); }, 8000);
            }
            showOAuthToast('Initiating OAuth for ' + name + '...', false);
            fetch('/api/servers/' + encodeURIComponent(name) + '/oauth/start', {method:'POST', headers:{'HX-Request':'true'}})
              .then(function(r2){ return r2.json().then(function(data2){ return {status:r2.status, data:data2}; }); })
              .then(function(res){
                if(res.status === 200 && res.data.auth_url){
                  showOAuthToast('Opening browser for authentication...', false);
                  window.open(res.data.auth_url, '_blank');
                  var attempts=0;
                  var interval=setInterval(function(){
                    attempts++;
                    if(attempts>60){ clearInterval(interval); showOAuthToast('OAuth timed out, try Refresh', true); return; }
                    fetch('/api/servers/' + encodeURIComponent(name) + '/oauth/status', {headers:{'HX-Request':'true'}})
                      .then(function(r3){ return r3.json(); })
                      .then(function(st){
                        if(st.status === 'completed'){
                          clearInterval(interval);
                          showOAuthToast('OAuth successful! Refreshing...', false);
                          var tbody=document.getElementById('server-table-body');
                          if(tbody){
                            fetch('/dashboard/servers', {headers:{'HX-Request':'true'}})
                              .then(function(r4){ return r4.text(); })
                              .then(function(html){
                                var tmp=document.createElement('template'); tmp.innerHTML=html.trim();
                                var newTbody=tmp.content.querySelector('#server-table-body');
                                if(newTbody && tbody.parentNode) tbody.parentNode.replaceChild(newTbody, tbody);
                                var newStats=tmp.content.querySelector('#dashboard-stats');
                                if(newStats){
                                  var cur=document.getElementById('dashboard-stats');
                                  if(cur) cur.outerHTML=newStats.outerHTML;
                                }
                              });
                          }
                        }
                      }).catch(function(){});
                  }, 2000);
                } else {
                  var errMsg = (res.data && res.data.detail) ? res.data.detail : 'OAuth failed to start';
                  showOAuthToast(errMsg, true);
                }
              }).catch(function(err){
                showOAuthToast('OAuth error: ' + err, true);
              });
          })(serverName);
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
    setupGlobalErrorToast();
    setupRevealVisibility();
    setupToastAutoHide();
    setupHeaderToast();
    setupRevealToggle();
    syncType();
    syncOAuth();
  }

  document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("htmx:load", init);
  if (document.readyState !== "loading") init();
})();
