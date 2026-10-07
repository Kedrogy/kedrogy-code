// Same-origin requests use Vite locally and the deployment reverse proxy.
export const API = (import.meta.env.VITE_API_ORIGIN ?? "").replace(/\/$/, "");
