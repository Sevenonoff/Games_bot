import { defineConfig } from "vitest/config";
import preact from "@preact/preset-vite";

// Сборка живёт по /app/ (так её отдаёт сервер из M1). Под `npm run dev` те же адреса
// /ws, /img и /dev проксируются на dev-сервер 8448, чтобы фронт не знал разницы.
export default defineConfig({
  base: "/app/",
  plugins: [preact()],
  server: {
    proxy: {
      "/ws": { target: "http://127.0.0.1:8448", ws: true },
      "/img": { target: "http://127.0.0.1:8448" },
      "/dev": { target: "http://127.0.0.1:8448" },
    },
  },
  build: { assetsInlineLimit: 0 },
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.{ts,tsx}"],
  },
});
