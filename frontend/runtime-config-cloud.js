// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
// Cloud runtime configuration template
console.log("🔧 Loading runtime config...");
window.RUNTIME_CONFIG = {
  authMethod: "cognito_auth",
  awsRegion: "REPLACE_WITH_REGION",
  userPoolId: "REPLACE_WITH_USER_POOL_ID",
  userPoolClientId: "REPLACE_WITH_CLIENT_ID",
  backendUrl: "/api",
  websocketUrl: "/ws",
  appName: "IRIS", // 👈 EDIT THIS to change app name
};
console.log("🔧 Runtime config loaded:", window.RUNTIME_CONFIG);
