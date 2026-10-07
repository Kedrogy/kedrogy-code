# Kedrogy web interface

This is a React and TypeScript application built with Vite.

```sh
npm ci
npm run dev
```

The local interface runs at `http://127.0.0.1:5173`. API requests are proxied to
`http://127.0.0.1:8002` by default. Set `VITE_DEV_API_TARGET` to use another local
backend. The deployment image uses the same-origin reverse proxy instead.

```sh
npm run build
node --experimental-strip-types --test tests/*.test.mjs
```

Model classes are an ordered JSON string array. Editing classes changes the next
training draft; predictions use the class mapping of the loaded training run.
The model page polls runtime serving health independently from startup task
completion. A stale or unavailable health observation disables prediction.

Train and Serve retain their idempotency key after an ambiguous network error.
A deliberate new operation after completion gets a new key. Stop the currently
loaded serving revision before switching to a newly published model.
