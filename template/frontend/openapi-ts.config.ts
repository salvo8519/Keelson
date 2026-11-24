import { defineConfig } from "@hey-api/openapi-ts"

export default defineConfig({
  // The API contract kept in the repository (scripts/openapi.py).
  input: "../openapi/openapi.json",
  output: "./src/client",

  plugins: [
    { name: "@hey-api/client-axios", throwOnError: true },
    { name: "@hey-api/typescript", case: "preserve" },
    {
      name: "@hey-api/sdk",
      operations: {
        // NOTE: this doesn't allow tree-shaking
        strategy: "byTags",
        methods: "static",
        containerName: "{{name}}Service",
        methodName: (name: string): string => name.replace(/^[^-]*-/, ""),
      },
    },
  ],
})
