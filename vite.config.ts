import react from "@vitejs/plugin-react";
import { defineConfig } from "vite-plus";

const API_TARGET = process.env.SKYROUTE_API ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
  fmt: {
    ignorePatterns: [
      "backend/**",
      "dist/**",
      "public/apidocs*",
      "project.md",
      "DESIGN.md",
      "*.lock",
    ],
  },
  lint: {
    ignorePatterns: ["backend/**", "dist/**", "public/apidocs*"],
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
    rules: { "vite-plus/prefer-vite-plus-imports": "error" },
    options: { typeAware: true, typeCheck: true },
  },
});
