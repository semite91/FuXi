import react from '@vitejs/plugin-react';
import { loadEnv, type Plugin } from 'vite';
import { defineConfig } from 'vitest/config';

const ENV_DIRECTORY = '..';
const API_URL_KEY = 'VITE_FUXI_API_URL';
const RAG_URL_KEY = 'VITE_FUXI_RAG_URL';
// Font files are never inlined as data: URIs, because the policy allows fonts only from the app.
const FONT_FILE = /\.(woff2?|ttf|otf)$/;
// The dev server and the preview of the build use the same port, the origin that
// the setup script allows in FUXI_CORS_ORIGINS.
const APP_PORT = 5173;
const TEST_ENVIRONMENT = 'jsdom';
const TEST_SETUP_FILE = './src/test/setup.ts';
// A fixed zone with an offset, so local and UTC times differ in tests.
const TEST_TIME_ZONE = 'Europe/Istanbul';

/**
 * Adds the Content-Security-Policy to the built page. The dev server injects inline
 * scripts and styles for hot reload, so the policy is left out there.
 */
const contentSecurityPolicy = (connectSources: readonly string[]): Plugin => ({
  name: 'fuxi-content-security-policy',
  apply: 'build',
  transformIndexHtml: () => [
    {
      tag: 'meta',
      injectTo: 'head-prepend',
      attrs: {
        'http-equiv': 'Content-Security-Policy',
        content: [
          "default-src 'self'",
          "script-src 'self'",
          "style-src 'self'",
          "font-src 'self'",
          "img-src 'self' data:",
          `connect-src 'self' ${connectSources.join(' ')}`.trim(),
          "manifest-src 'self'",
          "worker-src 'self'",
          "object-src 'none'",
          "base-uri 'self'",
          "form-action 'none'",
        ].join('; '),
      },
    },
  ],
});

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ENV_DIRECTORY, 'VITE_');
  const connectSources = [env[API_URL_KEY], env[RAG_URL_KEY]].filter((url): url is string => Boolean(url));

  return {
    plugins: [react(), contentSecurityPolicy(connectSources)],
    envDir: ENV_DIRECTORY,
    server: { port: APP_PORT, strictPort: true },
    preview: { port: APP_PORT, strictPort: true },
    build: {
      assetsInlineLimit: (filePath: string) => (FONT_FILE.test(filePath) ? false : undefined),
    },
    test: {
      environment: TEST_ENVIRONMENT,
      setupFiles: [TEST_SETUP_FILE],
      env: { TZ: TEST_TIME_ZONE },
    },
  };
});
