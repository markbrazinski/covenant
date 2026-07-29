import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RecordApp } from "./RecordApp";

/** Entry for the integrated Record-system build, mounted from `/index.html`. */
const el = document.getElementById("record-root");
if (el) {
  createRoot(el).render(
    <StrictMode>
      <RecordApp />
    </StrictMode>
  );
}
