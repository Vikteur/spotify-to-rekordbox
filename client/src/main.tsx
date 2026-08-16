import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { GuestApp } from './guest/GuestApp';
import './styles/tokens.css';
import './styles/app.css';
import './styles/guest.css';

// Magic links land on /g/<token>: guests (couple or friends) get the intake
// flow, everything else is the DJ app. No router dependency needed for two routes.
const guestMatch = window.location.pathname.match(/^\/g\/([^/]+)\/?$/);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {guestMatch ? <GuestApp token={decodeURIComponent(guestMatch[1])} /> : <App />}
  </StrictMode>,
);
