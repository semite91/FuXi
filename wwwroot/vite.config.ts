import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const ENV_DIRECTORY = '..';
const TEST_ENVIRONMENT = 'jsdom';

export default defineConfig({
  plugins: [react()],
  envDir: ENV_DIRECTORY,
  test: {
    environment: TEST_ENVIRONMENT,
  },
});
