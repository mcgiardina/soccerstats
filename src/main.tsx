import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import { CONFIG } from "./config";

// Team colours enter the stylesheet as --team-*; index.css derives --primary / --us / --accent
// from them per theme (dark mode lifts the text roles toward white).
document.documentElement.style.setProperty("--team-primary", CONFIG.colors.primary);
document.documentElement.style.setProperty("--team-accent", CONFIG.colors.accent);
document.documentElement.style.setProperty("--font", `"${CONFIG.font}", system-ui, sans-serif`);
document.documentElement.style.setProperty("--display", `"${CONFIG.displayFont}", "${CONFIG.font}", system-ui, sans-serif`);
document.title = CONFIG.appName;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);
