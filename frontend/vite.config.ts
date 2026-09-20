import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, /v1 and /healthz are proxied to the FastAPI server so the browser stays same-origin
// (no CORS, and the API key never leaves the page's own origin).
const api = process.env.AUTOPITCH_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/v1": api, "/healthz": api } },
});
