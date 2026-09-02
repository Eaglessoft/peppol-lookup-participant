/*
 * Page loader for the standalone Peppol Participant Lookup.
 *
 * Deliberately thin. The widget in embed/embed.js is served to third parties by
 * jsDelivr as one self-contained file, so it cannot import from here - which
 * means the dependency can only run in this direction. Keeping the render logic
 * there rather than copying it means the page and the embed can never drift,
 * at the cost of this page loading the widget script.
 */
(function () {
    'use strict';

    var script = document.createElement('script');
    script.src = 'embed/embed.js?v=2';
    script.defer = true;
    document.head.appendChild(script);
})();
