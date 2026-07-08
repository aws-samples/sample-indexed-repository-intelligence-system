// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App.jsx";

// Don't configure Amplify here - do it dynamically in App.jsx when runtime config is ready

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
