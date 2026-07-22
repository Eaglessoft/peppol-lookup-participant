# Embed Integration Guide

Use the widget with one script and one HTML tag.
The API service must be running and reachable from the browser.

```html
<peppol-lookup api-url="https://your-api.example.com"></peppol-lookup>
<script src="https://your-cdn.example.com/embed.js"></script>
```

## API URL Resolution

API URL is resolved in this order:

1. `api-url` attribute on `<peppol-lookup>`
2. `data-api-url` on the script tag
3. Built-in default: `http://localhost:8080`

## CSS Loading

The widget loads `embed.css` automatically by default.

Disable auto CSS:

```html
<peppol-lookup auto-css="false"></peppol-lookup>
```

Use a custom CSS URL:

```html
<script src="./embed.js" data-css-url="https://cdn.example.com/embed.css"></script>
```

## Full Page Layout

Use the same component as a full-page tool:

```html
<peppol-lookup api-url="https://your-api.example.com" layout="full"></peppol-lookup>
```

## Endpoints Used

- `GET {api-base}/api/v1/companies?mode=detail`
- `GET {api-base}/api/v1/codelists/participant-countries`

The widget uses company discovery as the primary flow. Participant lookup is still available
from the public API for direct Peppol participant IDs, but the embedded UI does not call it
directly.
