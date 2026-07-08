// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
// Simplified app configuration with runtime injection fallback
export const getAppConfig = () => {
  // Check if we have runtime config (CDK deployment)
  const runtimeConfig = window.RUNTIME_CONFIG;
  const isDev = import.meta.env.DEV;

  return {
    // App info
    appName:
      runtimeConfig?.appName ||
      import.meta.env.VITE_APP_NAME ||
      "IRIS",

    // Backend URLs - runtime config (CDK) takes precedence, then env vars (dev), then defaults
    backendUrl:
      runtimeConfig?.backendUrl ||
      import.meta.env.VITE_BACKEND_URL ||
      (isDev ? "http://localhost:8000" : "/api"),
    websocketUrl:
      runtimeConfig?.websocketUrl ||
      import.meta.env.VITE_WEBSOCKET_URL ||
      (isDev ? "ws://localhost:8000/ws" : "/ws"),

    // Auth configuration - CDK always has auth, dev can disable it
    authEnabled: runtimeConfig
      ? runtimeConfig.authMethod !== "none"
      : isDev
        ? false
        : true,

    // Cognito (from runtime config or env vars)
    cognito: {
      region:
        runtimeConfig?.awsRegion ||
        import.meta.env.VITE_AWS_REGION ||
        "us-east-1",
      userPoolId:
        runtimeConfig?.userPoolId || import.meta.env.VITE_USER_POOL_ID || "",
      userPoolClientId:
        runtimeConfig?.userPoolClientId ||
        import.meta.env.VITE_USER_POOL_CLIENT_ID ||
        "",
    },
  };
};

export default getAppConfig;
