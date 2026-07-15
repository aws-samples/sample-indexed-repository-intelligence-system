// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
    // Note: the app invokes the AgentCore Runtime entrypoint directly at
    // localAgentUrl (http://localhost:8080) in dev, so no proxy is required.
    // This proxy is kept only as a convenience for any relative /invocations call.
    proxy: {
      "/invocations": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
