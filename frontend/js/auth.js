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