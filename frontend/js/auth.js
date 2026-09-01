// ERP System — auth guard
// Loaded on every page. The session is owned by the server: the backend sets
// an automatic erp_session cookie on login and checks it on every /api call,
// so the browser never stores credentials and pages just work—the program
// itself keeps the user logged in. (A stored token from an older version is
// still sent if present, but it's no longer required.)

(function () {
  const TOKEN_KEY = "erp_session_token"; // legacy fallback only
  const LOGIN_URL = "/pages/login.html";

  window.ERPAuth = {
    token() {
      return localStorage.getItem(TOKEN_KEY);
    },
    setToken(t) {
      localStorage.setItem(TOKEN_KEY, t);
    },
    clear() {
      localStorage.removeItem(TOKEN_KEY);
    },
    isLoginPage() {
      return location.pathname === LOGIN_URL || location.pathname.endsWith("/login.html");
    },
    redirectToLogin() {
      if (this.isLoginPage()) return;
      this.clear();
      location.href = LOGIN_URL;
    },
    async ensure() {
      // Ask the server whether this browser has a live session (via the
      // automatic cookie); no local token is needed.
      try {
        const res = await fetch("/api/auth/me");
        if (!res.ok) this.redirectToLogin();
      } catch (e) {
        this.redirectToLogin();
      }
    },
  };

  const realFetch = window.fetch.bind(window);

  window.fetch = async function (input, init) {
    init = init || {};
    init.headers = new Headers(init.headers || {});

    const url = typeof input === "string" ? input : input.url;
    const isApi = url.startsWith("/api/") || url.startsWith("api/") || new URL(url, location.href).pathname.startsWith("/api/");
    const isAuthCall = url.includes("/api/auth/");
    const token = window.ERPAuth.token();

    if (isApi && !isAuthCall && token) {
      init.headers.set("Authorization", "Bearer " + token);
    }

    const res = await realFetch(input, init);

    if (res.status === 401 && isApi && !isAuthCall && !window.ERPAuth.isLoginPage()) {
      window.ERPAuth.redirectToLogin();
    }
    return res;
  };

  // Login page: if the server already has a session for this browser (cookie
  // valid), go straight to the dashboard instead of asking again.
  if (window.ERPAuth.isLoginPage()) {
    fetch("/api/auth/me").then((r) => { if (r.ok) location.href = "/pages/dashboard.html"; });
  } else {
    // FIX (security): the guard was defined but never actually called, so
    // every page opened freely with no login required. Enforce it now: if
    // the server has no live cookie for this browser, bounce to login.
    window.ERPAuth.ensure();
  }

  // Global logout: any element with [data-logout] (the sidebar "تسجيل الخروج"
  // links on every page) ends the session and returns to the login page.
  document.addEventListener("click", async (e) => {
    const el = e.target.closest("[data-logout]");
    if (!el) return;
    e.preventDefault();
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch (err) {}
    window.ERPAuth.clear();
    location.href = "/pages/login.html";
  });

  // ---- Global header icons (bell / help / mobile menu) --------------------
  // These were decorative placeholders repeated on every page. Give them a real
  // (simple) behaviour via delegation so every page gets it for free.

  // A lightweight reusable toast.
  let toastEl = null;
  function showToast(msg, ok) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.style.cssText = "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:9999;padding:12px 20px;border-radius:10px;font-family:Cairo,sans-serif;font-size:14px;font-weight:600;color:#fff;box-shadow:0 4px 20px rgba(0,0,0,.2);max-width:90vw;text-align:center;transition:opacity .3s;";
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.style.background = ok ? "#00b894" : "#dc3545";
    toastEl.style.opacity = "1";
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(() => { toastEl.style.opacity = "0"; }, 2600);
  }

  // Identify header icon buttons by their inner material-symbol icon name.
  function nearestActionBtn(target) {
    const btn = target.closest("button");
    if (!btn) return null;
    const icon = btn.querySelector(".material-symbols-outlined");
    const label = icon ? icon.textContent.trim() : "";
    return { btn, label };
  }

  document.addEventListener("click", async (e) => {
    if (e.target.closest("[data-logout]") || e.target.closest("a[href]")) return;
    const hit = nearestActionBtn(e.target);
    if (!hit) return;
    const { btn, label } = hit;

    if (label === "notifications") {
      // Open a live notifications sheet: latest invoices + repairs.
      if (document.getElementById("erp-notif-sheet")) {
        document.getElementById("erp-notif-sheet").remove();
        return;
      }
      let items = [];
      try {
        const r = await fetch("/api/dashboard/summary");
        if (r.ok) items = (await r.json()).activity || [];
      } catch (err) {}
      const sheet = document.createElement("div");
      sheet.id = "erp-notif-sheet";
      sheet.style.cssText = "position:fixed;top:64px;left:16px;z-index:9998;width:320px;max-width:88vw;background:#fff;border:1px solid #e0e0e0;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.18);font-family:Cairo,sans-serif;max-height:70vh;overflow:auto;";
      sheet.innerHTML = `<div style="padding:12px 16px;border-bottom:1px solid #eef1f5;font-weight:700;color:#181c1f;font-size:14px;">الإشعارات</div>` +
        (items.length ? items.map(a => {
          const t = a.type === "invoice" ? `فاتورة #${a.number || ""}` : `إصلاح #${a.number || ""}`;
          const s = a.type === "invoice" ? `مبلغ ${a.total || 0} ج.م` : (a.device || "");
          return `<div style="padding:10px 16px;border-bottom:1px solid #f1f4f8;font-size:13px;"><div style="color:#00407e;font-weight:600;">${t}</div><div style="color:#727783;margin-top:2px;">${s}</div></div>`;
        }).join("") : `<div style="padding:16px;color:#888;font-size:13px;">لا توجد إشعارات</div>`);
      document.body.appendChild(sheet);
      document.addEventListener("click", function closeNotif(e2) {
        if (!e2.target.closest("#erp-notif-sheet") && !e2.target.closest("button")) {
          const s = document.getElementById("erp-notif-sheet");
          if (s) s.remove();
          document.removeEventListener("click", closeNotif);
        }
      });
      return;
    }

    if (label === "help_outline") {
      showToast("لو محتاج مساعدة، كلمنا من صفحة الإعدادات", true);
      return;
    }

    if (label === "menu" && window.innerWidth < 768) {
      // Mobile: toggle the sidebar (the md:hidden menu button).
      const aside = document.querySelector("aside");
      if (aside) {
        const visible = aside.style.display === "flex";
        if (visible) {
          aside.style.display = "";
        } else {
          aside.style.display = "flex";
          aside.style.position = "fixed";
          aside.style.zIndex = "9997";
        }
      } else {
        showToast("افتح القائمة من الزر بالأسفل", true);
      }
      return;
    }
  });
})();