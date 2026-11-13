import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import App from './app';
import { listenForNavigation } from './services/service_worker_message_service';
import '@fontsource/manrope/latin-500.css';
import '@fontsource/manrope/latin-ext-500.css';
import '@fontsource/manrope/latin-600.css';
import '@fontsource/manrope/latin-ext-600.css';
import '@fontsource/manrope/latin-700.css';
import '@fontsource/manrope/latin-ext-700.css';
import '@fontsource/manrope/latin-800.css';
import '@fontsource/manrope/latin-ext-800.css';
import './css/main.less';

const ROOT_ELEMENT_ID = 'root';
const SERVICE_WORKER_PATH = '/service_worker.js';
const PAGE_LOAD_EVENT = 'load';

const registerServiceWorker = (): void => {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  window.addEventListener(PAGE_LOAD_EVENT, () => {
    navigator.serviceWorker.register(SERVICE_WORKER_PATH).catch((error: unknown) => {
      console.error('Service worker registration failed.', error);
    });
  });
};

const renderApp = (): void => {
  const rootElement = document.getElementById(ROOT_ELEMENT_ID);

  if (!rootElement) {
    throw new Error(`Element #${ROOT_ELEMENT_ID} was not found.`);
  }

  createRoot(rootElement).render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  );
};

registerServiceWorker();
listenForNavigation();
renderApp();
