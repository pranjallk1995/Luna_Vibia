import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev` serves the app with hot reload and sends data requests to the gateway.
const gateway = "http://127.0.0.1:18506";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": gateway, "/app": gateway, "/auth": gateway },
  },
});
