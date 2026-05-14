(function () {
    'use strict';

    const DEFAULT_API_BASE_URL = 'http://localhost:8080';
    const DEFAULT_CSS_URL = 'embed.css';
    const ROOT_CLASS = 'peppol-lookup-widget';

    function currentScript() {
        return document.currentScript || document.getElementsByTagName('script')[document.scripts.length - 1];
    }

    function normalizeApiUrl(value) {
        if (!value || typeof value !== 'string') return '';
        return value.trim().replace(/\/+$/, '');
    }

    function resolveApiUrl(element) {
        const script = currentScript();
        return normalizeApiUrl(element.getAttribute('api-url')) ||
            normalizeApiUrl(script && script.getAttribute('data-api-url')) ||
            DEFAULT_API_BASE_URL;
    }

    function ensureCssLoaded(enabled) {
        if (!enabled || document.querySelector('link[data-peppol-lookup-css="true"]')) return;
        const script = currentScript();
        const cssUrl = script && script.getAttribute('data-css-url') || DEFAULT_CSS_URL;
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = cssUrl;
        link.setAttribute('data-peppol-lookup-css', 'true');
        document.head.appendChild(link);
    }

    class PeppolLookupElement extends HTMLElement {
        connectedCallback() {
            if (this.initialized) return;
            this.initialized = true;

            const apiUrl = resolveApiUrl(this);
            ensureCssLoaded(this.getAttribute('auto-css') !== 'false');

            this.classList.add(ROOT_CLASS);
            this.innerHTML = `
                <div class="peppol-lookup-header">
                    <h1>Peppol Lookup</h1>
                    <p data-status>Checking API...</p>
                </div>
                <button type="button" data-refresh>Refresh</button>
            `;

            const status = this.querySelector('[data-status]');
            const refresh = this.querySelector('[data-refresh]');
            const load = () => {
                status.textContent = 'Checking API...';
                fetch(`${apiUrl}/health`)
                    .then((response) => response.ok ? response.json() : Promise.reject(new Error('API unavailable')))
                    .then((data) => {
                        status.textContent = `API status: ${data.status || 'unknown'}`;
                    })
                    .catch((error) => {
                        status.textContent = error.message;
                    });
            };

            refresh.addEventListener('click', load);
            load();
        }
    }

    if (!customElements.get('peppol-lookup')) {
        customElements.define('peppol-lookup', PeppolLookupElement);
    }
})();

