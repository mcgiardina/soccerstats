import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { CONFIG } from "./config";

document.documentElement.style.setProperty("--primary", CONFIG.colors.primary);
document.documentElement.style.setProperty("--accent", CONFIG.colors.accent);
document.documentElement.style.setProperty("--us", CONFIG.colors.primary);
document.documentElement.style.setProperty("--font", `"${CONFIG.font}", system-ui, sans-serif`);
document.documentElement.style.setProperty("--display", `"${CONFIG.displayFont}", "${CONFIG.font}", system-ui, sans-serif`);
document.title = CONFIG.appName;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
