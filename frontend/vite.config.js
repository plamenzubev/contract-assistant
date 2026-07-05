import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev server on :5173. We proxy /api to Django (:8000) to avoid
// CORS headaches so the frontend can just call fetch("/api/...").
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Explicitly 127.0.0.1 (not "localhost") — Node resolves localhost to IPv6 ::1,
      // but Django runserver listens only on IPv4, so the proxy would fail.
      "/api": "http://127.0.0.1:8000",
    },
  },
});
