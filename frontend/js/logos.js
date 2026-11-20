/*
 * Web-only logo helpers (majors only).
 *
 * LogoKit and Logostream terms require HOTLINKING from the browser (no server-side
 * storage/proxy) and both look up by ticker symbol only. So this file builds
 * img.logokit.com / api.logostream.dev URLs in the browser for a server-supplied
 * MAJORS allowlist only. Anything else (and any failure) gets a local letter
 * placeholder, never a broken image. Cardano native tokens use the server's
 * /api/mobile/token-logo path, not this.
 *
 * Keys come from the session-authenticated GET /api/config/public (DB-backed API
 * settings). When no key is set the server returns empty values and every
 * helper returns the placeholder.
 */
(function () {
    'use strict';
    var cfg = { token: '', lsKey: '', majors: {} };

    function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); }

    function placeholder(symbol) {
        var ch = esc(((symbol || '?') + '').trim().charAt(0).toUpperCase() || '?');
        var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="#3a3f4b"/>' +
            '<text x="16" y="21" font-family="Arial,sans-serif" font-size="15" font-weight="700" text-anchor="middle" fill="#d6d9e0">' + ch + '</text></svg>';
        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }

    function isMajor(symbol) {
        return !!cfg.majors[((symbol || '') + '').trim().toUpperCase()];
    }

    function logokitUrl(symbol, size) {
        var sym = ((symbol || '') + '').trim().toUpperCase();
        if (!cfg.token || !isMajor(sym)) return placeholder(sym);
        return 'https://img.logokit.com/crypto/' + encodeURIComponent(sym) +
            '?token=' + encodeURIComponent(cfg.token) + (size ? '&size=' + encodeURIComponent(size) : '');
    }

    function logostreamUrl(symbol) {
        var sym = ((symbol || '') + '').trim().toUpperCase();
        if (!cfg.lsKey || !isMajor(sym)) return '';
        return 'https://api.logostream.dev/cryptos/' + encodeURIComponent(sym) + '?key=' + encodeURIComponent(cfg.lsKey);
    }

    // Logo resolution for an <img>: LogoKit -> (on error) Logostream -> placeholder.
    // Logostream is only requested when LogoKit's image fails (20K/month quota).
    function onImgError(e) {
        var img = e.target;
        if (!img || img.tagName !== 'IMG') return;
        var src = img.getAttribute('src') || '';
        var fromLk = src.indexOf('https://img.logokit.com/') === 0;
        var fromLs = src.indexOf('https://api.logostream.dev/') === 0;
        if (!fromLk && !fromLs) return;
        e.stopPropagation();
        var m = src.match(/\/crypto\/([^?]+)|\/cryptos\/([^?]+)/);
        var sym = m ? decodeURIComponent(m[1] || m[2]) : '?';
        if (fromLk && !img.dataset.lsTried) {
            img.dataset.lsTried = '1';
            var ls = logostreamUrl(sym);
            if (ls) { img.src = ls; return; }
        }
        if (img.dataset.phSet) return;
        img.dataset.phSet = '1';
        img.src = placeholder(sym);
    }
    document.addEventListener('error', onImgError, true);

    // <img data-logo-symbol="BTC" data-logo-size="32"> placeholders in static HTML
    function hydrate(root) {
        (root || document).querySelectorAll('img[data-logo-symbol]').forEach(function (img) {
            img.src = logokitUrl(img.getAttribute('data-logo-symbol'), img.getAttribute('data-logo-size') || 32);
        });
    }

    var ready = null;
    function init() {
        if (ready) return ready;
        ready = fetch('/api/config/public', { credentials: 'include' })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (d) {
                cfg.token = d.logokit_token || '';
                cfg.lsKey = d.logostream_key || '';
                cfg.majors = {};
                (d.logo_majors || []).forEach(function (s) { cfg.majors[s] = true; });
                hydrate();
            })
            .catch(function () { /* keep placeholders */ });
        return ready;
    }

    document.addEventListener('DOMContentLoaded', function () { init().then(function () { hydrate(); }); });

    window.initLogokitToken = init;
    window.getLogoKitUrl = logokitUrl;
    window.getLogostreamUrl = logostreamUrl;
    window.logoPlaceholder = placeholder;
    window.isMajorLogoSymbol = isMajor;
    window.hydrateLogos = hydrate;
    window.ABCT_LOGOS_READY = init();
})();
