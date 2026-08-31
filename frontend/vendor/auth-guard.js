/**
 * ERP System — auth guard.
 *
 * Included at the very top of <head> on every page except login.html.
 * - If there's no stored session token, redirects to the login page
 *   immediately (before the rest of the page or its data loads).
 * - Patches window.fetch so every call to a same-origin /api/... path
 *   automatically gets an `Authorization: Bearer <token>` header — no
 *   page's own script needs to know about auth at all.
 * - If any API call comes back 401 (expired/invalid session), clears the
 *   stored session and bounces to the login page.
 *
 * This file is NOT downloaded by vendor_assets.py — it's part of the app
 * itself, not a third-party asset, so it works offline from the start.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "erp_session";
    var LOGIN_PATH = "/pages/login.html";

    function getSession() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function clearSession() {
        localStorage.removeItem(STORAGE_KEY);
    }

    function goToLogin() {
        if (!location.pathname.endsWith("/login.html")) {
            location.href = LOGIN_PATH;
        }
    }

    var session = getSession();
    if (!session || !session.token) {
        goToLogin();
        return; // don't bother patching fetch — we're leaving this page
    }

    window.erpCurrentUser = session.user || null;

    var originalFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        init = init || {};
        var url = typeof input === "string" ? input : (input && input.url) || "";
        var isApiCall = url.indexOf("/api/") === 0 || url.indexOf(location.origin + "/api/") === 0;

        if (isApiCall) {
            init.headers = Object.assign({}, init.headers, {
                Authorization: "Bearer " + session.token,
            });
        }

        return originalFetch(input, init).then(function (res) {
            if (isApiCall && res.status === 401) {
                clearSession();
                goToLogin();
            }
            return res;
        });
    };

    window.erpLogout = function () {
        originalFetch("/api/auth/logout", {
            method: "POST",
            headers: { Authorization: "Bearer " + session.token },
        }).finally(function () {
            clearSession();
            goToLogin();
        });
    };
})();
