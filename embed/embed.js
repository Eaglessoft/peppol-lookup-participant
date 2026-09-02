(function () {
    'use strict';

    const DEFAULT_CSS_URL = '/embed/embed.css';

    function defaultApiUrl() {
        const script = currentScript();
        const scriptSource = script && script.getAttribute('src');
        if (scriptSource) {
            try {
                const scriptUrl = new URL(scriptSource, window.location.href);
                const basePath = scriptUrl.pathname.replace(/\/embed\/embed\.js$/, '');
                return normalizeUrl(`${scriptUrl.origin}${basePath}`);
            } catch (error) {
                // Fall back to the current origin when the browser cannot parse the script URL.
            }
        }
        return normalizeUrl(window.location.origin);
    }

    function defaultCssUrl() {
        const script = currentScript();
        const scriptSource = script && script.getAttribute('src');
        if (scriptSource) {
            try {
                const scriptUrl = new URL(scriptSource, window.location.href);
                scriptUrl.pathname = scriptUrl.pathname.replace(/\/embed\.js$/, '/embed.css');
                scriptUrl.search = '';
                return scriptUrl.toString();
            } catch (error) {
                // Fall back to the built-in embed path when the script URL is not parseable.
            }
        }
        return DEFAULT_CSS_URL;
    }

    const FALLBACK_COUNTRIES = [
        'AT', 'AU', 'BE', 'BG', 'CH', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI',
        'FR', 'GB', 'GR', 'HR', 'HU', 'IE', 'IS', 'IT', 'LI', 'LT', 'LU', 'LV',
        'MT', 'NL', 'NO', 'NZ', 'PL', 'PT', 'RO', 'SE', 'SG', 'SI', 'SK', 'US'
    ];

    function currentScript() {
        return document.currentScript ||
            document.getElementsByTagName('script')[document.scripts.length - 1];
    }

    function normalizeUrl(value) {
        if (!value || typeof value !== 'string') return '';
        return value.trim().replace(/\/+$/, '');
    }

    function resolveApiUrl(element) {
        const script = currentScript();
        return normalizeUrl(element.getAttribute('api-url')) ||
            normalizeUrl(script && script.getAttribute('data-api-url')) ||
            defaultApiUrl();
    }

    function ensureCssLoaded(element) {
        if (element.getAttribute('auto-css') === 'false') return;
        if (document.querySelector('link[data-peppol-lookup-css="true"]')) return;

        const script = currentScript();
        const cssUrl = script && script.getAttribute('data-css-url') || defaultCssUrl();
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = cssUrl;
        link.setAttribute('data-peppol-lookup-css', 'true');
        document.head.appendChild(link);
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function capabilityLabel(capability) {
        const documentValue = capability.documentTypeIdentifier &&
            capability.documentTypeIdentifier.value || 'Document';
        const processValue = capability.processIdentifier &&
            capability.processIdentifier.value || '';
        return `
            <li>
                <strong>${escapeHtml(documentValue)}</strong>
                ${processValue ? `<span>${escapeHtml(processValue)}</span>` : ''}
            </li>
        `;
    }

    function statusText(item, fallback) {
        return item && (item.status || item.codeListStatus || item.transportProfileStatus) ||
            fallback || 'unknown';
    }

    function endpointTransport(process) {
        const endpoint = process && process.endpoints && process.endpoints[0];
        if (!endpoint) return null;
        return {
            value: endpoint.transportProfile,
            status: endpoint.transportProfileStatus
        };
    }

    function serviceCapabilityLabel(service, environmentName) {
        const documentType = service.documentTypeIdentifier || {};
        const process = service.processes && service.processes[0] || {};
        const processIdentifier = process.processIdentifier || {};
        const transport = endpointTransport(process);
        const documentStatus = statusText(documentType);
        const processStatus = statusText(processIdentifier);
        const transportStatus = statusText(transport);
        return `
            <li class="pl-dti-row">
                <div>
                    <div class="pl-doc-title">
                        <span class="pl-doc-badge">${escapeHtml(documentTypeLabel(documentType))}</span>
                        <code>${escapeHtml(documentType.value || 'Document type')}</code>
                    </div>
                    <div class="pl-doc-meta">
                        ${processIdentifier.value ? `
                            <span>Process: ${escapeHtml(processIdentifier.value)}</span>
                        ` : ''}
                        ${transport && transport.value ? `
                            <span>Transport: ${escapeHtml(transportLabel(transport.value))}</span>
                        ` : ''}
                    </div>
                </div>
                <div class="pl-status-stack">
                    <span data-code-status="${escapeHtml(documentStatus)}">
                        ${escapeHtml(statusLabel('DTI', documentStatus))}
                    </span>
                    ${processIdentifier.value ? `
                        <span data-code-status="${escapeHtml(processStatus)}">
                            ${escapeHtml(statusLabel('Process', processStatus))}
                        </span>
                    ` : ''}
                    ${transport && transport.value ? `
                        <span data-code-status="${escapeHtml(transportStatus)}">
                            ${escapeHtml(statusLabel('Transport', transportStatus))}
                        </span>
                    ` : ''}
                </div>
            </li>
        `;
    }

    function transportLabel(value) {
        if (value === 'peppol-transport-as4-v2_0') return 'Peppol AS4 v2';
        return value || 'Transport profile';
    }

    function documentTypeLabel(documentType) {
        if (documentType && documentType.displayName) return documentType.displayName;
        const text = String(documentType && documentType.value || documentType || '');
        if (text.includes('ApplicationResponse') && text.includes('mlr')) {
            return 'Peppol Message Level Response transaction 3.0';
        }
        if (text.includes('ApplicationResponse') && text.includes('invoice_response')) {
            return 'Peppol Invoice Response transaction 3.0';
        }
        if (text.includes('CreditNote') && text.includes('selfbilling')) {
            return 'Peppol BIS Self-Billing UBL Credit Note V3';
        }
        if (text.includes('CreditNote') && text.includes('billing')) {
            return 'Peppol BIS Billing UBL Credit Note V3';
        }
        if (text.includes('Invoice') && text.includes('selfbilling')) {
            return 'Peppol BIS Self-Billing UBL Invoice V3';
        }
        if (text.includes('Invoice') && text.includes('billing')) {
            return 'Peppol BIS Billing UBL Invoice V3';
        }
        if (text.includes('Order')) {
            return 'Peppol BIS Order V3';
        }
        const local = text.split('::')[1] || text.split(':').pop() || 'Document type';
        return local.replace(/([a-z])([A-Z])/g, '$1 $2');
    }

    function statusLabel(name, status) {
        if (status === 'unsupported') return `${name} unsupported`;
        if (status === 'unknown') return `${name} status unknown`;
        return `${name} ${status}`;
    }

    function readableValue(value) {
        if (!value) return '';
        if (typeof value === 'string') return value;
        if (Array.isArray(value)) {
            return value.map(readableValue).filter(Boolean).join(', ');
        }
        if (typeof value === 'object') {
            return value.name || value.value || value.text || value.content ||
                Object.values(value).map(readableValue).filter(Boolean).join(' ');
        }
        return String(value);
    }

    function countryName(code) {
        const value = String(code || '').toUpperCase();
        try {
            if (typeof Intl !== 'undefined' && Intl.DisplayNames) {
                const displayNames = new Intl.DisplayNames(['en'], {type: 'region'});
                return displayNames.of(value) || value;
            }
        } catch (error) {
            return value;
        }
        return value;
    }

    function formatRegistrationDate(value) {
        if (!value) return '';
        const text = String(value);
        const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (!match) return text;
        const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
        return new Intl.DateTimeFormat('en', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        }).format(date);
    }

    function entityLabel(entity) {
        const name = readableValue(entity.name) || readableValue(entity.names) ||
            readableValue(entity.participantID) || 'Business entity';
        const participant = readableValue(entity.participantID) ||
            readableValue(entity.participantIdentifier) || '';
        const country = readableValue(entity.countryCode) || readableValue(entity.country);
        const geoInfo = readableValue(entity.geoInfo) || readableValue(entity.geographicalInformation);
        const additionalInfo = readableValue(entity.additionalInfo) ||
            readableValue(entity.additionalInformation);
        const websites = entityWebsites(entity);
        const identifiers = entityIdentifiers(entity);
        const contacts = entityContacts(entity);
        const registrationDate = formatRegistrationDate(entity.regDate || entity.registrationDate);
        return `
            <li class="pl-entity-row">
                <div class="pl-entity-main">
                    <div class="pl-entity-title">
                        <strong>${escapeHtml(name)}</strong>
                        ${country ? `<span>${escapeHtml(country)}</span>` : ''}
                    </div>
                    ${participant ? `<p>${escapeHtml(participant)}</p>` : ''}
                    ${geoInfo ? `<p>${escapeHtml(geoInfo)}</p>` : ''}
                    ${websites.length ? `
                        <dl class="pl-entity-fields">
                            <div>
                                <dt>Website URIs</dt>
                                <dd>
                                    ${websites.map((website, index) =>
                                        websiteLink(website, index + 1)
                                    ).join('')}
                                </dd>
                            </div>
                        </dl>
                    ` : ''}
                    ${identifiers.length ? `
                        <dl class="pl-entity-fields">
                            <div>
                                <dt>Additional identifiers</dt>
                                <dd>
                                    ${identifiers.map(identifierLabel).join('')}
                                </dd>
                            </div>
                        </dl>
                    ` : ''}
                    ${contacts.length ? `
                        <dl class="pl-entity-fields">
                            <div>
                                <dt>Contacts</dt>
                                <dd>
                                    ${contacts.map(contactLabel).join('')}
                                </dd>
                            </div>
                        </dl>
                    ` : ''}
                    ${additionalInfo ? `<p>${escapeHtml(additionalInfo)}</p>` : ''}
                </div>
                ${registrationDate ? `
                    <div class="pl-entity-meta">
                        <span>Registered</span>
                        <strong>${escapeHtml(registrationDate)}</strong>
                    </div>
                ` : ''}
            </li>
        `;
    }

    function entityWebsites(entity) {
        const value = entity.websites || entity.websiteURIs || entity.websiteUris ||
            entity.websiteURI || entity.websiteUri || entity.WebsiteURIs || [];
        const list = Array.isArray(value) ? value : [value];
        return list.map(readableValue).filter(Boolean);
    }

    function entityIdentifiers(entity) {
        const value = entity.identifiers || entity.additionalIdentifiers ||
            entity.additionalIdentifier || entity.AdditionalIdentifiers || [];
        const list = Array.isArray(value) ? value : [value];
        return list.map((identifier) => {
            if (!identifier || typeof identifier !== 'object') {
                return {scheme: '', value: readableValue(identifier)};
            }
            return {
                scheme: readableValue(identifier.scheme) || readableValue(identifier.type) ||
                    readableValue(identifier.schemeName) || readableValue(identifier.name),
                value: readableValue(identifier.value) || readableValue(identifier.identifier) ||
                    readableValue(identifier.id)
            };
        }).filter((identifier) => identifier.scheme || identifier.value);
    }

    function entityContacts(entity) {
        const value = entity.contacts || entity.contact || entity.Contacts || [];
        const list = Array.isArray(value) ? value : [value];
        return list.map((contact) => {
            if (!contact || typeof contact !== 'object') {
                return {type: '', name: readableValue(contact), phone: '', email: ''};
            }
            return {
                type: readableValue(contact.type) || readableValue(contact.contactType),
                name: readableValue(contact.name),
                phone: readableValue(contact.phone) || readableValue(contact.phoneNumber),
                email: readableValue(contact.email) || readableValue(contact.mail)
            };
        }).filter((contact) => contact.type || contact.name || contact.phone || contact.email);
    }

    function identifierLabel(identifier) {
        const scheme = identifier.scheme || 'Identifier';
        return `<span><strong>${escapeHtml(scheme)}</strong> ${escapeHtml(identifier.value)}</span>`;
    }

    function contactLabel(contact) {
        const parts = [contact.type, contact.name, contact.phone, contact.email].filter(Boolean);
        return `<span>${escapeHtml(parts.join(' - '))}</span>`;
    }

    function websiteLink(website, index) {
        const url = safeExternalUrl(website);
        const label = `${index}. ${website}`;
        if (!url) return `<span>${escapeHtml(label)}</span>`;
        return `
            <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
                ${escapeHtml(label)}
            </a>
        `;
    }

    function safeExternalUrl(value) {
        try {
            const url = new URL(String(value));
            return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
        } catch (error) {
            return '';
        }
    }

    function firstEndpoint(service) {
        const process = service && service.processes && service.processes[0];
        return process && process.endpoints && process.endpoints[0] || null;
    }

    function certificateSummary(certificate) {
        if (!certificate) return [];
        const fingerprints = certificate.fingerprints || {};
        return [
            ['Certificate subject', certificate.subject],
            ['Certificate issuer', certificate.issuer],
            ['Certificate serial', certificate.serialNumber],
            ['Certificate valid from', certificate.notBefore],
            ['Certificate valid until', certificate.notAfter],
            ['Certificate SHA-256', fingerprints.sha256]
        ].filter((item) => item[1]);
    }

    function technicalRows(entry) {
        const environment = entry.environment || {};
        const sml = environment.sml || {};
        const smp = environment.smp || {};
        const rows = [
            ['SMP URL', smp.baseUrl || sml.smpBaseUrl],
            ['NAPTR hostname', sml.queryName],
            ['NAPTR record', (sml.naptrRecords || []).join(' | ')]
        ];
        const firstService = (entry.services || [])[0];
        const endpoint = firstEndpoint(firstService);
        if (endpoint) {
            rows.push(
                ['Endpoint URL', endpoint.endpointReference],
                ['Technical contact', endpoint.technicalContactUrl],
                ['Technical information', endpoint.technicalInformationUrl],
                ['Service description', endpoint.serviceDescription],
                ['Business level signature', endpoint.requireBusinessLevelSignature === true ?
                    'required' : endpoint.requireBusinessLevelSignature === false ? 'not required' : ''],
                ['Minimum authentication', endpoint.minimumAuthenticationLevel],
                ['Service active from', endpoint.serviceActivationDate],
                ['Service expires', endpoint.serviceExpirationDate],
                ...certificateSummary(endpoint.certificate)
            );
        }
        return rows.filter((item) => item[1]);
    }

    function technicalDetails(entry) {
        const rows = technicalRows(entry);
        if (!rows.length) {
            return '<div class="pl-empty">No technical details available</div>';
        }
        return `
            <dl class="pl-tech-list">
                ${rows.map(([label, value]) => `
                    <div>
                        <dt>${escapeHtml(label)}</dt>
                        <dd>${escapeHtml(value)}</dd>
                    </div>
                `).join('')}
            </dl>
        `;
    }

    function directoryMatchLabel(item) {
        const participant = readableValue(item.participantID) ||
            readableValue(item.participantIdentifier) || readableValue(item.id);
        const name = readableValue(item.name) || readableValue(item.names) ||
            readableValue(item.entityName) || 'Directory result';
        const country = readableValue(item.countryCode) || readableValue(item.country) || '';
        return `
            <li>
                <strong>${escapeHtml(name)}</strong>
                <span>${escapeHtml([participant, country].filter(Boolean).join(' - '))}</span>
            </li>
        `;
    }

    function directoryEnvironment(directoryResult) {
        const baseUrl = String(directoryResult && directoryResult.baseUrl || '');
        return baseUrl.includes('test-directory') ? 'test' : 'prod';
    }

    function directoryParticipantValue(item) {
        const participant = item.participantID || item.participantId ||
            item.participantIdentifier || item.id;
        const value = readableValue(participant);
        const normalized = value.replace(/^iso6523-actorid-upis::/i, '');
        if (!looksLikeParticipantValue(normalized)) return '';
        return normalized;
    }

    function looksLikeParticipantValue(value) {
        return /^[A-Za-z0-9]{4}:.+/.test(String(value || '').trim());
    }

    function directoryEntityName(item) {
        const entities = item.entities || item.businessEntities ||
            item.businessCard && item.businessCard.entities || [];
        if (Array.isArray(entities) && entities.length) {
            return readableValue(entities[0].name) || readableValue(entities[0].names);
        }
        return readableValue(item.name) || readableValue(item.names) ||
            readableValue(item.entityName) || 'Directory result';
    }

    function directoryCountry(item) {
        const entities = item.entities || item.businessEntities ||
            item.businessCard && item.businessCard.entities || [];
        if (Array.isArray(entities) && entities.length) {
            return readableValue(entities[0].countryCode) || readableValue(entities[0].country);
        }
        return readableValue(item.countryCode) || readableValue(item.country);
    }
    function environmentTitle(name) {
        if (name === 'prod') return 'Production';
        if (name === 'test') return 'Test';
        return name || 'Environment';
    }

    function countryOptions(selected, countryCodes) {
        const placeholder = `
            <option value="" ${selected ? '' : 'selected'} disabled>Select country</option>
        `;
        return placeholder + (countryCodes || FALLBACK_COUNTRIES).map((code) => `
            <option value="${code}" ${code === selected ? 'selected' : ''}>
                ${countryName(code)} (${code})
            </option>
        `).join('');
    }

    function checkedLabel(entry, routable) {
        if (routable) return '';
        if ((entry.sourceHits || []).some((source) =>
            source.endsWith(':sml') || source.endsWith(':smk')
        )) {
            return 'SMP unavailable';
        }
        return 'Checked';
    }

    function sourceLabel(source) {
        const name = String(source || '').split(':').pop();
        if (name === 'directory') return 'Directory';
        if (name === 'sml') return 'SML';
        if (name === 'smk') return 'SMK';
        if (name === 'smp') return 'SMP';
        if (name === 'lookup') return 'Lookup';
        return name || 'Source';
    }

    function sourceChips(sources) {
        return (sources || []).map((source) => `
            <span class="pl-source-chip" data-source="${escapeHtml(String(source || '').split(':').pop())}">
                ${escapeHtml(sourceLabel(source))}
            </span>
        `).join('');
    }

    function mergeSourceHits(existing = [], incoming = []) {
        return Array.from(new Set([...(existing || []), ...(incoming || [])]));
    }

    function rejectedCandidateReason(candidate) {
        if (candidate.rejectionReason) return candidate.rejectionReason;
        if (candidate.validationStatus === 'candidate_valid') return 'not found';
        return candidate.validationStatus || 'not found';
    }

    class PeppolLookupElement extends HTMLElement {
        connectedCallback() {
            if (this.initialized) return;
            this.initialized = true;
            this.apiUrl = resolveApiUrl(this);
            this.countryCodes = FALLBACK_COUNTRIES;
            ensureCssLoaded(this);
            this.classList.add('peppol-lookup-widget');
            if (this.getAttribute('layout') === 'full') {
                this.classList.add('pl-full');
            }
            this.render();
            this.bind();
            this.loadCountryOptions();
        }

        bind() {
            this.querySelector('[data-form]').addEventListener('submit', (event) => {
                event.preventDefault();
                this.lookupCompany(false);
            });
            this.querySelector('[data-result]').addEventListener('click', (event) => {
                const refresh = event.target.closest('[data-refresh-results]');
                if (refresh) {
                    this.lookupCompany(true);
                    return;
                }
                const button = event.target.closest('[data-detail-participant]');
                if (button) return;
                const toggle = event.target.closest('[data-toggle-panel]');
                if (!toggle) return;
                const target = this.querySelector(`#${toggle.getAttribute('data-toggle-panel')}`);
                if (!target) return;
                const hidden = target.hasAttribute('hidden');
                target.toggleAttribute('hidden', !hidden);
                toggle.textContent = hidden ?
                    toggle.getAttribute('data-open-label') || 'Hide details' :
                    toggle.getAttribute('data-closed-label') || 'Show details';
            });
        }

        async loadCountryOptions() {
            try {
                const response = await fetch(`${this.apiUrl}/api/v1/codelists/participant-countries`);
                const payload = await response.json();
                if (!response.ok || !Array.isArray(payload.countries)) return;
                this.countryCodes = payload.countries;
                const select = this.querySelector('select[name="country"]');
                if (!select) return;
                const selected = select.value || '';
                select.innerHTML = countryOptions(selected, this.countryCodes);
                if (this.countryCodes.includes(selected)) {
                    select.value = selected;
                }
            } catch (error) {
                return;
            }
        }

        async lookupCompany(refresh = false) {
            const form = new FormData(this.querySelector('[data-form]'));
            this.startLookupProgress(refresh);

            const params = new URLSearchParams({
                country: form.get('country') || '',
                identifier: form.get('identifier') || '',
                identifier_type: form.get('identifierType') || '',
                mode: 'detail'
            });

            // Empty means "whatever the service is configured for", which is
            // how this endpoint behaved before the field existed. Sending
            // prod,test explicitly would take that decision away from the
            // deployment.
            const environments = form.get('environments');
            if (environments) params.set('environments', environments);

            // Empty means the service decides, and its default is both.
            this.requestedEnvironments = environments ? environments.split(',') : ['prod', 'test'];

            if (refresh) params.set('refresh', 'true');

            try {
                const response = await fetch(`${this.apiUrl}/api/v1/companies?${params}`);
                const payload = await response.json();
                if (!response.ok) throw new Error(payload.detail || 'Lookup failed');
                this.stopLookupProgress();
                this.renderCompanyResult(payload);
            } catch (error) {
                this.stopLookupProgress();
                this.renderError(error);
            }
        }

        startLookupProgress(refresh = false) {
            const steps = [
                'Generating participant candidates',
                'Searching production and test directory',
                'Checking SML and SMK routing',
                'Fetching SMP document types',
                'Finalizing results'
            ];
            const stepThresholds = [0, 18, 38, 62, 82];
            const startedAt = performance.now();
            const render = () => {
                const elapsed = performance.now() - startedAt;
                const progress = Math.min(92, Math.round(92 * (1 - Math.exp(-elapsed / 3600))));
                const activeIndex = stepThresholds.reduce(
                    (current, threshold, index) => progress >= threshold ? index : current,
                    0
                );
                this.setResult(`
                    <article class="pl-card pl-loading">
                        <div class="pl-loading-overview" aria-label="Lookup in progress">
                            <div class="pl-progress-ring" aria-hidden="true" style="--progress: ${progress * 3.6}deg">
                                <strong>${progress}%</strong>
                            </div>
                            <div>
                                <strong>${refresh ? 'Refreshing live Peppol data' : 'Looking up participant'}</strong>
                                <span>${escapeHtml(steps[activeIndex])}</span>
                                <small>Live Peppol sources may take a few seconds to respond.</small>
                            </div>
                        </div>
                        <div class="pl-loading-steps">
                            ${steps.map((step, index) => `
                                <div class="pl-loading-step" data-progress="${
                                    index < activeIndex ? 'done' :
                                        index === activeIndex ? 'active' : 'pending'
                                }">
                                    <strong>${escapeHtml(step)}</strong>
                                </div>
                            `).join('')}
                        </div>
                    </article>
                `);
            };
            this.stopLookupProgress();
            render();
            this.loadingTimer = window.setInterval(() => {
                render();
            }, 120);
        }

        stopLookupProgress() {
            if (!this.loadingTimer) return;
            window.clearInterval(this.loadingTimer);
            this.loadingTimer = null;
        }

        renderCompanyResult(payload) {
            const matches = payload.matches || [];
            const candidates = payload.candidates || [];
            const directoryMatches = payload.directoryMatches || [];
            const prodCount = this.environmentEntries(matches, directoryMatches, 'prod').length;
            const testCount = this.environmentEntries(matches, directoryMatches, 'test').length;
            const environmentsShown = this.activeEnvironments();
            const found = environmentsShown.reduce(
                (total, name) => total + (name === 'prod' ? prodCount : testCount), 0
            );
            this.setResult(`
                <div class="pl-results-toolbar">
                    <div class="pl-found-badge" data-empty="${found === 0}">
                        ${found === 0 ? 'No participants found' : `Found ${found} participant${found === 1 ? '' : 's'}`}
                    </div>
                    <button type="button" class="pl-result-refresh" data-refresh-results
                        aria-label="Refresh results from live Peppol sources">
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M20 6v5h-5M4 18v-5h5M6.1 9a7 7 0 0 1 11.5-2.4L20 9M4 15l2.4 2.4A7 7 0 0 0 17.9 15"/>
                        </svg>
                        <span>Refresh results</span>
                    </button>
                </div>
                <div class="pl-summary">
                    <span><strong>${matches.length}</strong> matches</span>
                    ${environmentsShown.includes('prod') ? `<span><strong>${prodCount}</strong> production</span>` : ''}
                    ${environmentsShown.includes('test') ? `<span><strong>${testCount}</strong> test</span>` : ''}
                </div>
                ${this.environmentSections(matches, directoryMatches)}
                ${this.notFoundCandidateList(candidates)}
                ${this.rejectedCandidateList(candidates)}
                <section data-detail class="pl-detail"></section>
            `);
        }

        environmentSections(matches, directoryMatches = []) {
            return this.activeEnvironments().map((name) =>
                this.environmentSection(matches, directoryMatches, name)
            ).join('');
        }

        // Falls back to both so a result rendered before any search - or by an
        // embedder driving the widget directly - still shows everything.
        activeEnvironments() {
            const requested = this.requestedEnvironments;
            return Array.isArray(requested) && requested.length ? requested : ['prod', 'test'];
        }

        environmentEntries(matches, directoryMatches, name) {
            const networkEntries = matches.flatMap((match) => {
                const environment = (match.environments || []).find((item) => item.name === name);
                if (!environment) return [];
                const services = environment.smp && environment.smp.services || [];
                const directory = environment.directory;
                const sourceHits = (match.summary && match.summary.foundIn || [])
                    .filter((source) => source.startsWith(`${name}:`));
                const found = environment.status === 'found' ||
                    services.length ||
                    sourceHits.length ||
                    Boolean(directory && directory.found);
                const normalized = match.input && match.input.normalized || {};
                return found ? [{
                    match,
                    participant: normalized.value ||
                        match.participantIdentifier && match.participantIdentifier.value || '',
                    environment,
                    services,
                    sourceHits
                }] : [];
            });
            const byParticipant = new Map();
            for (const entry of networkEntries) {
                const normalized = entry.match.input && entry.match.input.normalized || {};
                byParticipant.set(String(normalized.value || '').toLowerCase(), entry);
            }
            for (const entry of this.directorySearchEntries(directoryMatches, name)) {
                const existing = byParticipant.get(String(entry.participant || '').toLowerCase());
                if (existing) {
                    existing.directorySearch = entry;
                    existing.sourceHits = mergeSourceHits(existing.sourceHits, entry.sourceHits);
                } else {
                    byParticipant.set(String(entry.participant || '').toLowerCase(), entry);
                }
            }
            return Array.from(byParticipant.values()).filter((entry) => entry.participant !== '');
        }

        directorySearchEntries(directoryMatches, name) {
            return directoryMatches
                .filter((result) => directoryEnvironment(result) === name)
                .flatMap((result) => {
                    const card = result.businessCard || {};
                    const matches = Array.isArray(card.matches) ? card.matches : [];
                    return matches.flatMap((item) => {
                        const participant = directoryParticipantValue(item);
                        if (!participant) return [];
                        return [{
                            participant,
                            directoryOnly: true,
                            name: directoryEntityName(item),
                            country: directoryCountry(item),
                            entities: this.directoryEntities({matches: [item]}),
                            environment: {name, status: 'directory'},
                            services: [],
                            sourceHits: [`${name}:directory`]
                        }];
                    });
                });
        }

        environmentSection(matches, directoryMatches, name) {
            const entries = this.environmentEntries(matches, directoryMatches, name);
            return `
                <article class="pl-card pl-env-section" data-env="${escapeHtml(name)}">
                    <header>
                        <strong>${escapeHtml(environmentTitle(name))}</strong>
                        <span>${entries.length} participant(s)</span>
                    </header>
                    ${entries.length ? entries.map((entry) =>
                        this.environmentParticipant(entry)
                    ).join('') : `
                        <div class="pl-empty">No ${escapeHtml(environmentTitle(name).toLowerCase())} result</div>
                    `}
                </article>
            `;
        }

        environmentParticipant(entry) {
            const normalized = entry.match && entry.match.input && entry.match.input.normalized || {};
            const participant = entry.participant ||
                normalized.value ||
                entry.match && entry.match.participantIdentifier &&
                    entry.match.participantIdentifier.value ||
                'Participant';
            const services = entry.services || [];
            const directorySearch = entry.directorySearch;
            const entities = (
                this.environmentDirectoryEntities(entry.environment).length ?
                    this.environmentDirectoryEntities(entry.environment) :
                    directorySearch && directorySearch.entities || []
            ).slice(0, 8);
            const routable = services.length > 0 ||
                entry.sourceHits.some((source) => source.endsWith(':smp'));
            const dtiId = `pl-dti-${String(entry.environment.name || 'env')}-${participant}`
                .replace(/[^a-zA-Z0-9_-]/g, '-');
            const techId = `pl-tech-${String(entry.environment.name || 'env')}-${participant}`
                .replace(/[^a-zA-Z0-9_-]/g, '-');
            return `
                <section class="pl-env-participant">
                    <header>
                        <div>
                            <strong>${escapeHtml(participant)}</strong>
                            ${entry.sourceHits.length ? `
                                <div class="pl-source-chips">
                                    ${sourceChips(entry.sourceHits)}
                                </div>
                            ` : ''}
                        </div>
                        <div class="pl-participant-actions">
                            ${services.length ? `
                                <button type="button" class="pl-secondary-button"
                                    data-toggle-panel="${escapeHtml(dtiId)}"
                                    data-open-label="Hide document types"
                                    data-closed-label="Show document types">
                                    Show document types
                                </button>
                            ` : `<span class="pl-muted-action">${escapeHtml(checkedLabel(entry, routable))}</span>`}
                            <button type="button" class="pl-secondary-button"
                                data-toggle-panel="${escapeHtml(techId)}"
                                data-open-label="Hide technical details"
                                data-closed-label="Show technical details">
                                Show technical details
                            </button>
                        </div>
                    </header>
                    ${(entry.directoryOnly || directorySearch) && !entities.length ? `
                        <div class="pl-directory-summary">
                            <strong>${escapeHtml(
                                entry.name || directorySearch && directorySearch.name ||
                                    'Directory company'
                            )}</strong>
                            <span>${escapeHtml(
                                entry.country || directorySearch && directorySearch.country || ''
                            )}</span>
                        </div>
                    ` : ''}
                    ${entities.length ? `
                        <div class="pl-directory-block">
                            <strong>Directory companies</strong>
                            <ul>${entities.map(entityLabel).join('')}</ul>
                        </div>
                    ` : ''}
                    ${services.length ? `
                        <div class="pl-dti-block" id="${escapeHtml(dtiId)}" hidden>
                            <header>
                                <strong>Document type identifiers</strong>
                                <span>${services.length} DTI(s)</span>
                            </header>
                            <ul>
                                ${services.map((service) => serviceCapabilityLabel(service, '')).join('')}
                            </ul>
                        </div>
                    ` : ''}
                    <div class="pl-tech-block" id="${escapeHtml(techId)}" hidden>
                        <header>
                            <strong>Technical details</strong>
                            <span>SML / SMP / endpoint</span>
                        </header>
                        ${technicalDetails(entry)}
                    </div>
                </section>
            `;
        }

        environmentDirectoryEntities(environment) {
            const directory = environment && environment.directory;
            if (!directory || !directory.businessCard) return [];
            return this.directoryEntities(directory.businessCard);
        }

        directoryList(directoryMatches) {
            return `
                <article class="pl-card">
                    <header>
                        <strong>Directory matches</strong>
                        <span>${directoryMatches.length} source result(s)</span>
                    </header>
                    <ul>
                        ${directoryMatches.slice(0, 3).map((match) => {
                            const card = match.businessCard || {};
                            const matches = card.matches || [];
                            const entities = this.directoryEntities(card).slice(0, 5);
                            if (entities.length) {
                                return entities.map(entityLabel).join('');
                            }
                            if (matches.length) {
                                return matches.slice(0, 5).map((item) => {
                                    return directoryMatchLabel(item);
                                }).join('');
                            }
                            return '<li><strong>Directory result</strong></li>';
                        }).join('')}
                    </ul>
                </article>
            `;
        }

        directoryEntities(card) {
            if (Array.isArray(card.entities)) return card.entities;
            if (card.businessCard && Array.isArray(card.businessCard.entities)) {
                return card.businessCard.entities;
            }
            if (Array.isArray(card.matches)) {
                return card.matches.flatMap((match) => {
                    if (Array.isArray(match.entities)) return match.entities;
                    if (match.businessCard && Array.isArray(match.businessCard.entities)) {
                        return match.businessCard.entities;
                    }
                    return [];
                });
            }
            return [];
        }

        rejectedCandidateList(candidates) {
            const rejected = candidates.filter((candidate) => candidate.rejectionReason ||
                candidate.validationStatus === 'candidate_rejected');
            if (!rejected.length) return '';
            return `
                <details class="pl-card pl-rejected">
                    <summary>
                        <strong>Invalid candidate formats</strong>
                        <span>${rejected.length} checked</span>
                    </summary>
                    <ul>
                        ${rejected.map((candidate) => {
                            const participant = candidate.participantIdentifier || {};
                            return `
                                <li>
                                    <strong>${escapeHtml(participant.value)}</strong>
                                    <span>${escapeHtml(rejectedCandidateReason(candidate))}</span>
                                </li>
                            `;
                        }).join('')}
                    </ul>
                </details>
            `;
        }

        notFoundCandidateList(candidates) {
            const notFound = candidates.filter((candidate) =>
                !candidate.found &&
                !candidate.rejectionReason &&
                candidate.validationStatus !== 'candidate_rejected'
            );
            if (!notFound.length) return '';
            return `
                <details class="pl-card pl-rejected">
                    <summary>
                        <strong>Checked but not found</strong>
                        <span>${notFound.length} candidate(s)</span>
                    </summary>
                    <ul>
                        ${notFound.map((candidate) => {
                            const participant = candidate.participantIdentifier || {};
                            return `
                                <li>
                                    <strong>${escapeHtml(participant.value)}</strong>
                                    <span>${escapeHtml(candidate.schemeName || candidate.schemeCode || '')}</span>
                                </li>
                            `;
                        }).join('')}
                    </ul>
                </details>
            `;
        }

        detailServices(payload) {
            return (payload.environments || []).flatMap((environment) => {
                const services = environment.smp && environment.smp.services || [];
                return services.map((service) => ({
                    environment: environment.name,
                    service
                }));
            });
        }

        resultCard(payload) {
            if (payload.summary) {
                const normalized = payload.input && payload.input.normalized || {};
                const foundIn = payload.summary.foundIn || [];
                const services = this.detailServices(payload);
                return `
                    <article class="pl-card">
                        <header>
                            <strong>${escapeHtml(normalized.value || 'Participant')}</strong>
                            <span>
                                ${payload.summary.routable ? 'routable' : 'not routable'}
                                ${services.length ? ` - ${services.length} DTI(s)` : ''}
                            </span>
                        </header>
                        <div class="pl-summary">
                            <span>${foundIn.length ?
                                escapeHtml(foundIn.join(', ')) : 'not found'}</span>
                        </div>
                    </article>
                `;
            }
            const participant = payload.participantIdentifier || {};
            const entities = payload.businessEntities || [];
            const capabilities = payload.documentCapabilities || [];
            return `
                <article class="pl-card">
                    <header>
                        <strong>${escapeHtml(participant.value || 'Participant')}</strong>
                        <span>${capabilities.length} capabilities</span>
                    </header>
                    ${entities.length ? `<ul>${entities.slice(0, 3).map(entityLabel).join('')}</ul>` : ''}
                    ${capabilities.length ?
                        `<ul>${capabilities.slice(0, 5).map(capabilityLabel).join('')}</ul>` :
                        '<div class="pl-empty">No document capability found</div>'}
                </article>
            `;
        }

        renderError(error) {
            this.setResult(`
                <div class="pl-alert">
                    <strong>Error</strong>
                    <span>${escapeHtml(error.message || 'Lookup failed')}</span>
                </div>
            `);
        }

        setResult(html) {
            this.querySelector('[data-result]').innerHTML = html;
        }

        setDetail(html, targetId) {
            const detail = targetId ?
                this.querySelector(`#${CSS.escape(targetId)}`) :
                this.querySelector('[data-detail]');
            if (detail) detail.innerHTML = html;
            if (detail) detail.hidden = false;
        }

        render() {
            this.innerHTML = `
                <section class="pl-shell">
                    <main class="pl-main">
                        <section class="pl-search-band">
                            <form data-form class="pl-form">
                                <div class="pl-grid">
                                    <label>
                                        <span>Country <b class="pl-required">*</b></span>
                                        <select name="country" required>
                                            ${countryOptions('', this.countryCodes)}
                                        </select>
                                    </label>
                                    <label>
                                        <span>Identifier <b class="pl-required">*</b></span>
                                        <input name="identifier" required
                                            placeholder="Company VAT/Tax ID, e.g. 0123456789">
                                    </label>
                                    <label>
                                        <span>Type / ICD</span>
                                        <input name="identifierType"
                                            placeholder="Peppol scheme code, e.g. 0208">
                                    </label>
                                    <label>
                                        <span>Peppol Network</span>
                                        <select name="environments">
                                            <option value="prod" selected>Production</option>
                                            <option value="test">Test</option>
                                            <option value="">Both</option>
                                        </select>
                                    </label>
                                </div>
                                <button type="submit">Search Peppol</button>
                            </form>
                        </section>
                        <section data-result class="pl-result">
                            <div class="pl-empty">Results will appear here. Pick a country and enter an identifier to search.</div>
                        </section>
                    </main>
                </section>
            `;
        }
    }

    if (!customElements.get('peppol-lookup')) {
        customElements.define('peppol-lookup', PeppolLookupElement);
    }
})();
