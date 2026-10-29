import { defineConfig, devices } from "@playwright/test";

// APP_URL = deployed app (enables test_e2e_deployed.spec.ts); LOCAL_URL = local dev server.
const BASE_URL = process.env.APP_URL || process.env.LOCAL_URL || "http://localhost:5173";

export default defineConfig({
  testDir: "./",
  testMatch: ["test_frontend.spec.ts", "test_e2e_deployed.spec.ts"],
  timeout: 60_000,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "../test-results/html", open: "never" }]],
  use: {
    baseURL: BASE_URL,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
