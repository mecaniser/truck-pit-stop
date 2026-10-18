import React from "react";
import ReactDOM from "react-dom/client";
import ConnectedInbox from "../../src/features/communications/ConnectedInbox";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConnectedInbox />
  </React.StrictMode>,
);
