# chat-vue3

Self-contained Vue 3 + Vite frontend project. Run `npm install`, `npm run build`,
and `npm run dev` from this directory after generating the API clients.

`src/gen/` is generated. `src/App.vue`, `src/api.ts`, `vite.config.ts`,
`openapi-ts.config.ts`, and `package.json` are handwritten.

- Buf ES emits TypeScript contracts into `src/gen/chat/v1/` and the required
  Google HTTP annotations into `src/gen/google/api/` (`include_imports: true`).
- Hey API emits the typed REST client into `src/gen/rest/`.
- `npm run generate:rest` consumes the OpenAPI file from `proto/chat/gen/openapi/rest/`.

The project has its own `.gitignore` so `node_modules`, build output, and
generated clients stay out of an extracted Git repository.

The app uses the local Vite proxy to reach FastAPI/ConnectRPC on port 8000.
