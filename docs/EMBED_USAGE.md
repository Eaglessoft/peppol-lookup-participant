# Embed Integration Guide

Use the widget with one script and one HTML tag.

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

## Endpoints Used

- `GET {api-base}/health`

