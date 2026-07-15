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

    // AgentCore Runtime — the browser invokes the Runtime data-plane endpoint
    // directly using this ARN + region. Injected via window.RUNTIME_CONFIG (CDK)
    // or VITE_AGENT_RUNTIME_ARN (env).
    agentRuntimeArn:
      runtimeConfig?.agentRuntimeArn ||
      import.meta.env.VITE_AGENT_RUNTIME_ARN ||
      "",

    // Local dev only: when set, the client POSTs to this base URL's /invocations
    // instead of the AWS data-plane endpoint (e.g. `python agent_runtime.py`).
    localAgentUrl:
      runtimeConfig?.localAgentUrl ||
      import.meta.env.VITE_LOCAL_AGENT_URL ||
      (isDev ? "http://localhost:8080" : ""),

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
