import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../schema/openapi.rest.json',
  output: 'src/gen/rest',
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
  ],
});
