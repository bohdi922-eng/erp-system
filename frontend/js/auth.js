// ERP System — auth guard
// Loaded on every page. Wraps fetch so the session token is attached to all
// /api calls, and sends the user to /pages/login.html if the API says 401.

(function () {
  const TOKEN_KEY = "erp_session_token";
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
      // Verify the stored token still works (idempotent, cheap).
      if (!this.token()) { this.redirectToLogin(); return; }
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

  // Guard pages that must not be reachable logged-in already (login page).
  if (window.ERPAuth.isLoginPage() && window.ERPAuth.token()) {
    fetch("/api/auth/me").then((r) => { if (r.ok) location.href = "/pages/dashboard.html"; });
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
})();