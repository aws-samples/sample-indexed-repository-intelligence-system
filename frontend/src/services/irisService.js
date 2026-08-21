// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// IRIS service — Amazon Bedrock AgentCore Runtime transport.
//
// Replaces the previous WebSocket transport. The browser invokes the AgentCore
// Runtime directly over HTTPS and reads a Server-Sent Events (SSE) stream:
//
//   POST {endpoint}/runtimes/{arn}/invocations?qualifier=DEFAULT
//   Authorization: Bearer <Cognito JWT>
//   X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: <session id>
//
// The backend (backend/agent_runtime.py) already reshapes Strands events into
// IRIS's event envelope (status / stream_chunk / tool_use / complete / error),
// so this client keeps the same handleWebSocketMessage logic and the same public
// API (connect / disconnect / reconnect / subscribe / sendMessage / loadConfig /
// getCodebaseInfo / generateContext). App.jsx and Chat.jsx are unchanged.

import { getAppConfig } from "../config/appConfig.js";
import { fetchAuthSession } from "aws-amplify/auth";

class IrisService {
  constructor() {
    this.subscribers = new Set();
    this.messageId = 1;
    this.isConnected = false;
    this.currentResponse = ""; // accumulated assistant text for the in-flight reply
    this.announcedTools = new Set();
    this.sessionId = null; // AgentCore runtimeSessionId (stable across turns)
    this._inFlight = null; // AbortController for the current invocation
  }

  // ---- config accessors -----------------------------------------------------

  get _cfg() {
    return getAppConfig();
  }

  /** Direct AgentCore Runtime invocation URL, or a local dev endpoint. */
  _invocationUrl() {
    const cfg = this._cfg;
    // Local dev: talk straight to `python agent_runtime.py` on :8080.
    if (cfg.localAgentUrl) {
      return `${cfg.localAgentUrl.replace(/\/$/, "")}/invocations`;
    }
    const region = cfg.cognito?.region || "us-east-1";
    const arn = cfg.agentRuntimeArn;
    if (!arn) {
      throw new Error("Agent Runtime ARN not configured");
    }
    const endpoint = `https://bedrock-agentcore.${region}.amazonaws.com`;
    return `${endpoint}/runtimes/${encodeURIComponent(arn)}/invocations?qualifier=DEFAULT`;
  }

  /**
   * AgentCore requires a runtimeSessionId of at least 33 characters. Generate one
   * per chat and reuse it across turns so the Runtime keeps the same microVM (and
   * therefore the same in-memory conversation history).
   *
   * The session id keys server-side conversation state, so it is generated with
   * crypto.getRandomValues (a CSPRNG) rather than Math.random. getRandomValues is
   * used directly instead of crypto.randomUUID because randomUUID is only exposed
   * in secure contexts, which would otherwise force a weak fallback path.
   */
  _ensureSessionId() {
    if (!this.sessionId) {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      const raw = Array.from(bytes, (b) =>
        b.toString(16).padStart(2, "0"),
      ).join("");
      // "iris-" + 32 hex chars = 37 characters, clearing the 33 char minimum.
      this.sessionId = `iris-${raw}`;
    }
    return this.sessionId;
  }

  async _getAuthToken() {
    // Local/anonymous dev has no auth; return null and proceed.
    if (this._cfg.authEnabled === false) return null;
    try {
      const session = await fetchAuthSession();
      // Send the ACCESS token, not the ID token. The Runtime's Cognito JWT
      // authorizer is configured with `allowedClients`, which validates the
      // `client_id` claim. Cognito access tokens carry `client_id`; ID tokens
      // carry `aud` instead and would be rejected with a 403.
      return session.tokens?.accessToken?.toString() || null;
    } catch (e) {
      console.log("No auth token available");
      return null;
    }
  }

  // ---- connection lifecycle (no persistent socket now) ----------------------
  // Kept for API compatibility with App.jsx / Chat.jsx. There is no long-lived
  // connection to AgentCore; "connecting" just means the service is ready.

  async connect() {
    this._ensureSessionId();
    this.isConnected = true;
    return Promise.resolve();
  }

  disconnect() {
    if (this._inFlight) {
      this._inFlight.abort();
      this._inFlight = null;
    }
    this.isConnected = false;
    this.subscribers.clear();
  }

  async reconnect() {
    // Start a fresh conversation session on explicit reconnect.
    this.sessionId = null;
    this._ensureSessionId();
    this.isConnected = true;
    this.emit({
      type: "connection_success",
      message: "Reconnected successfully",
    });
  }

  // ---- messaging ------------------------------------------------------------

  async sendMessage(content) {
    const messageId = this.messageId++;
    // Reset per-reply accumulators.
    this.currentResponse = "";
    this.announcedTools.clear();

    const url = this._invocationUrl();
    const sessionId = this._ensureSessionId();
    const token = await this._getAuthToken();

    const headers = {
      "Content-Type": "application/json",
      "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sessionId,
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    this._inFlight = new AbortController();

    // Signal "typing" so the UI shows the indicator (parity with old status event).
    this.emit({
      id: messageId,
      type: "typing",
      sender: "agent",
      timestamp: new Date().toISOString(),
    });

    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ prompt: content, runtimeSessionId: sessionId }),
        signal: this._inFlight.signal,
      });

      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        throw new Error(`HTTP ${response.status}: ${detail}`);
      }

      await this._readSSE(response);
    } catch (error) {
      if (error.name === "AbortError") return { id: messageId };
      console.error("Error invoking agent:", error);
      this.emit({
        id: this.messageId++,
        content: "Error: failed to reach IRIS service",
        timestamp: new Date().toISOString(),
        sender: "agent",
        type: "message",
      });
    } finally {
      this._inFlight = null;
    }

    return { id: messageId };
  }

  /** Read the SSE stream and route each `data:` frame through handleWebSocketMessage. */
  async _readSSE(response) {
    if (!response.body) return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          this._handleSSELine(line);
        }
      }
      if (buffer.trim()) this._handleSSELine(buffer);
    } finally {
      reader.releaseLock();
    }
  }

  _handleSSELine(line) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data: ")) return;
    const data = trimmed.slice(6);
    if (!data) return;
    try {
      const message = JSON.parse(data);
      // The AgentCore harness also emits a top-level {error, error_type} frame if
      // the server generator throws — normalize it to our envelope.
      if (message.error && !message.type) {
        this.handleWebSocketMessage({ type: "error", data: { error: message.error } });
        return;
      }
      this.handleWebSocketMessage(message);
    } catch (e) {
      console.debug("Failed to parse SSE frame:", data);
    }
  }

  // ---- config / read-only actions (via invocation payload) ------------------

  async _invokeAction(action) {
    const url = this._invocationUrl();
    const sessionId = this._ensureSessionId();
    const token = await this._getAuthToken();
    const headers = {
      "Content-Type": "application/json",
      "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sessionId,
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ action }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    // Actions return a single SSE frame; collect the first data payload.
    const text = await response.text();
    for (const line of text.split("\n")) {
      const t = line.trim();
      if (t.startsWith("data: ")) {
        try {
          return JSON.parse(t.slice(6)).data;
        } catch (e) {
          /* fall through */
        }
      }
    }
    return null;
  }

  async loadConfig() {
    try {
      const data = await this._invokeAction("config");
      return data || { codebase_dir: "./codebase", output_dir: ".iris_cache" };
    } catch (error) {
      console.error("Error loading config:", error);
      return { codebase_dir: "./codebase", output_dir: ".iris_cache" };
    }
  }

  async getCodebaseInfo() {
    try {
      return await this._invokeAction("codebase_info");
    } catch (error) {
      console.error("Error getting codebase info:", error);
      return null;
    }
  }

  async generateContext() {
    try {
      return await this._invokeAction("generate_context");
    } catch (error) {
      console.error("Error generating context:", error);
      return { status: "error", error: error.message };
    }
  }

  // ---- event handling (unchanged envelope from the old WebSocket server) -----

  handleWebSocketMessage(message) {
    switch (message.type) {
      case "auth_success":
        this.emit({
          type: "connection_success",
          message: "Connected and authenticated successfully",
        });
        break;

      case "stream_chunk":
        this.currentResponse += message.data.content;
        this.emit({
          id: message.message_id,
          content: message.data.content,
          fullContent: this.currentResponse,
          timestamp: new Date().toISOString(),
          sender: "agent",
          type: "partial_message",
        });
        break;

      case "tool_use": {
        const toolId = message.data.tool_id;
        if (toolId && !this.announcedTools.has(toolId)) {
          const toolEmojis = {
            load_codebase_overview_context: "🔧",
            read_multiple_files: "📚",
            read_notebook: "📓",
            file_read: "📖",
            file_retrieval_agent: "🧲",
            code_search_tool: "🔍",
          };
          const emoji = toolEmojis[message.data.tool_name] || "🔧";
          const transformedToolName = message.data.tool_name
            .replace(/_/g, " ")
            .replace(/(^|\s)\w/g, (m) => m.toUpperCase());
          const toolText = `\n\n> ${emoji} **Using tool: ${transformedToolName}**\n\n`;
          this.currentResponse += toolText;
          this.announcedTools.add(toolId);
          this.emit({
            id: message.message_id,
            content: toolText,
            fullContent: this.currentResponse,
            timestamp: new Date().toISOString(),
            sender: "agent",
            type: "partial_message",
          });
        }
        break;
      }

      case "complete":
        this.emit({
          id: message.message_id,
          content: this.currentResponse || "",
          timestamp: new Date().toISOString(),
          sender: "agent",
          type: "message",
        });
        this.currentResponse = "";
        this.announcedTools.clear();
        break;

      case "error":
        this.emit({
          id: this.messageId++,
          content: `Error: ${message.data.error}`,
          timestamp: new Date().toISOString(),
          sender: "agent",
          type: "message",
        });
        break;

      case "status":
        this.emit({
          id: message.message_id,
          type: "typing",
          sender: "agent",
          timestamp: new Date().toISOString(),
        });
        break;

      default:
        console.log("Unhandled message type:", message.type);
    }
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  emit(message) {
    this.subscribers.forEach((callback) => callback(message));
  }
}

export const irisService = new IrisService();
