// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
// Development runtime configuration - no auth.
// Local dev talks to a locally-run AgentCore Runtime entrypoint
// (backend/agent_runtime.py) at localAgentUrl instead of the AWS data-plane.
window.RUNTIME_CONFIG = {
  authMethod: "none",
  awsRegion: "us-east-1",
  userPoolId: "",
  userPoolClientId: "",
  localAgentUrl: "http://localhost:8080",
  appName: "IRIS",
};
