import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../../../proto/chat/gen/openapi/rest/chat/v1/chat.openapi.json',
  output: 'src/gen/rest',
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
  ],
});
