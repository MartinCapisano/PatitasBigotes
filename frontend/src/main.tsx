import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { initSentry } from "./lib/sentry";
import "./styles.css";

// No-op sin VITE_SENTRY_DSN. Antes del render para capturar errores tempranos.
initSentry();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
