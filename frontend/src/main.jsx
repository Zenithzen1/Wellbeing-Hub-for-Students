import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App.jsx';
import { SessionProvider } from './session.jsx';
import { ToastProvider } from './components/ui.jsx';
import './styles/app.css';

// Hash routes (/app/#/book) so FastAPI's StaticFiles can serve the app without a catch-all route.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <HashRouter>
      <ToastProvider>
        <SessionProvider>
          <App />
        </SessionProvider>
      </ToastProvider>
    </HashRouter>
  </StrictMode>,
);
