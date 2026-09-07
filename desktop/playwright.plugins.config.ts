import base from "./playwright.config";

// Plugin component tests mock IPC and do not need to rebuild or stop a daemon.
export default {
  ...base,
  testMatch: "builtin-plugins.spec.ts",
  webServer: { ...base.webServer, command: "npm exec -- vite --host 127.0.0.1 --port 1424" },
};
