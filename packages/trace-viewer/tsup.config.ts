import { copyFileSync } from "node:fs";
import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  dts: true,
  sourcemap: true,
  clean: true,
  target: "es2020",
  external: ["react", "react-dom", "react/jsx-runtime"],
  async onSuccess() {
    copyFileSync("src/styles.css", "dist/styles.css");
  },
});
