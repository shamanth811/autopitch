import "@fontsource/playfair-display/400.css";
import "@fontsource/lora/400.css";
import "@fontsource/lora/700.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/700.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
