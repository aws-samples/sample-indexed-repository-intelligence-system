// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
// Force rebuild v2
import { getAppConfig } from "../config/appConfig.js";
import { fetchAuthSession } from "aws-amplify/auth";

class IrisService {
  constructor() {
    // Don't set URLs in constructor - get them dynamically when needed
    this.subscribers = new Set();
    this.messageId = 1;
    this.websocket = null;
    this.isConnected = false;
    this.clientId = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.currentResponse = ""; // Track accumulated response
    this.announcedTools = new Set(); // Track announced tools
  }

  get baseUrl() {
    return getAppConfig().backendUrl;
  }

  get wsUrl() {
    return getAppConfig().websocketUrl;
  }

  // Configuration methods
  async loadConfig() {
    try {
      const response = await fetch(`${this.baseUrl}/config`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Error loading config:", error);
      // Return default config from environment variables or fallback
      return {
        codebase_dir:
          import.meta.env.VITE_CODEBASE_DIR ||
          import.meta.env.REACT_APP_CODEBASE_DIR ||
          "./codebase",
        output_dir:
          import.meta.env.VITE_OUTPUT_DIR ||
          import.meta.env.REACT_APP_OUTPUT_DIR ||
          ".iris_cache",
      };
    }
  }

  async validateTree(codebaseDir) {
    try {
      const response = await fetch(`${this.baseUrl}/validate-tree`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          codebase_dir: codebaseDir,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Error validating tree:", error);
      // Return mock data for development
      return this.getMockTreeValidation();
    }
  }

  async getCodebaseInfo() {
    try {
      const response = await fetch(`${this.baseUrl}/codebase-info`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Error getting codebase info:", error);
      // Return null when no data is available
      return null;
    }
  }

  async generateContext(codebaseDir, outputDir) {
    try {
      const response = await fetch(`${this.baseUrl}/generate-context`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          codebase_dir: codebaseDir,
          output_dir: outputDir,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Error generating context:", error);
      // Return mock success for development
      return {
        status: "update_complete",
        message: "Context generated successfully (mock)",
        processed_files: ["src/App.js", "src/components/Chat.js"],
      };
    }
  }

  async queryCodebase(userInput, codebaseDir, outputDir) {
    try {
      const response = await fetch(`${this.baseUrl}/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_input: userInput,
          codebase_dir: codebaseDir,
          output_dir: outputDir,
          streaming: true,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Handle streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      return {
        async *[Symbol.asyncIterator]() {
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value);
              const lines = chunk.split("\n");

              for (const line of lines) {
                if (line.trim() && line.startsWith("data: ")) {
                  const data = line.slice(6);
                  if (data !== "[DONE]") {
                    yield data;
                  }
                }
              }
            }
          } finally {
            reader.releaseLock();
          }
        },
      };
    } catch (error) {
      console.error("Error querying codebase:", error);
      // Return mock response for development
      return this.getMockResponse(userInput);
    }
  }

  async loadConversationHistory(outputDir) {
    try {
      const response = await fetch(
        `${this.baseUrl}/conversation-history?output_dir=${encodeURIComponent(outputDir)}`,
      );
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Error loading conversation history:", error);
      return [];
    }
  }

  async saveConversationHistory(conversationHistory, outputDir) {
    try {
      const response = await fetch(`${this.baseUrl}/conversation-history`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_history: conversationHistory,
          output_dir: outputDir,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Error saving conversation history:", error);
      return { success: false, error: error.message };
    }
  }

  async clearConversationHistory(outputDir) {
    try {
      const response = await fetch(`${this.baseUrl}/conversation-history`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          output_dir: outputDir,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error("Error clearing conversation history:", error);
      return { success: false, error: error.message };
    }
  }

  // Mock methods for development when backend is not available
  getMockTreeValidation() {
    return {
      has_changed: true,
      change_details: {
        new_files: [
          "mock/components/Configuration.js",
          "mock/components/TreeValidation.js",
        ],
        modified_files: ["mock/App.js"],
        deleted_files: [],
      },
      tree_display: `MOCK!! react-app/
├── src/
│   ├── App.js
│   ├── index.js
│   ├── components/
│   │   ├── Chat.js
│   │   ├── Configuration.js
│   │   └── TreeValidation.js
│   └── services/
│       ├── mockWebSocket.js
│       └── irisService.js
├── package.json
└── README.md`,
      total_files: 8,
      files_to_process: [
        "mock/components/Configuration.js",
        "mock/components/TreeValidation.js",
        "mock/App.js",
      ],
    };
  }

  async *getMockResponse(userInput) {
    const responses = [
      `I understand you're asking about "${userInput}". Let me analyze the codebase for you.`,
      `\n\nBased on my analysis of the React application, I can see that:`,
      `\n- It's a modern chat interface built with React and Tailwind CSS`,
      `\n- The current implementation uses a mock WebSocket service`,
      `\n- There are components for Chat, Configuration, and TreeValidation`,
      `\n\nThe codebase appears to be well-structured with separate concerns for UI components and services.`,
      `\n\nIs there anything specific about the code you'd like me to explain further?`,
    ];

    for (const chunk of responses) {
      await new Promise((resolve) => setTimeout(resolve, 200));
      yield chunk;
    }
  }

  // WebSocket connection management
  async connect() {
    return new Promise(async (resolve, reject) => {
      try {
        this.websocket = new WebSocket(this.wsUrl);

        // Get token for authentication message
        let authToken = null;
        try {
          const session = await fetchAuthSession();
          authToken = session.tokens?.idToken?.toString();
        } catch (authError) {
          console.log(
            "No auth token available, connecting without authentication",
          );
        }

        this.websocket.onopen = () => {
          console.log("Connected to WebSocket server");

          // Send authentication as first message if token exists (secure approach)
          if (authToken) {
            const authMessage = {
              type: "authenticate",
              token: authToken,
            };
            this.websocket.send(JSON.stringify(authMessage));
            console.log("Sent authentication message to WebSocket server");
          }

          this.isConnected = true;
          this.reconnectAttempts = 0;
          resolve();
        };

        this.websocket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this.handleWebSocketMessage(message);
          } catch (error) {
            console.error("Error parsing WebSocket message:", error);
          }
        };

        this.websocket.onclose = () => {
          console.log("WebSocket connection closed");
          this.isConnected = false;
          this.attemptReconnect();
        };

        this.websocket.onerror = (error) => {
          console.error("WebSocket error:", error);
          this.isConnected = false;
          reject(error);
        };
      } catch (error) {
        console.error("Error creating WebSocket connection:", error);
        reject(error);
      }
    });
  }

  disconnect() {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    this.isConnected = false;
    this.subscribers.clear();
  }

  /**
   * Manual reconnect - resets attempt counter and tries to connect
   * Use this when user explicitly wants to reconnect after timeout
   * Preserves existing subscribers and notifies them of reconnection
   */
  async reconnect() {
    // Disconnect any existing connection first (but preserve subscribers)
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
    this.isConnected = false;
    this.reconnectAttempts = 0; // Reset counter for manual reconnect

    await this.connect();

    // Notify subscribers of successful reconnection
    this.emit({
      type: "connection_success",
      message: "Reconnected successfully",
    });
  }

  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(
        `Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`,
      );

      setTimeout(() => {
        this.connect().catch((error) => {
          console.error("Reconnection failed:", error);
        });
      }, 2000 * this.reconnectAttempts); // Exponential backoff
    }
  }

  handleWebSocketMessage(message) {
    switch (message.type) {
      case "welcome":
        this.clientId = message.data.client_id;
        console.log("Received welcome message, client ID:", this.clientId);
        break;

      case "auth_success":
        console.log("WebSocket authentication successful");
        this.emit({
          type: "connection_success",
          message: "Connected and authenticated successfully",
        });
        break;

      case "auth_error":
        console.error(
          "WebSocket authentication failed:",
          message.message || message.data?.error,
        );
        this.emit({
          type: "error",
          error:
            "Authentication failed: " +
            (message.message || message.data?.error || "Invalid token"),
        });
        break;

      case "stream_chunk":
        // Accumulate streaming text chunks
        if (!this.currentResponse) {
          this.currentResponse = "";
        }
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

      case "tool_use":
        // Add tool notification to accumulated text (only once per tool)
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
            .replace(/(^|\s)\w/g, function (match) {
              return match.toUpperCase();
            });
          const toolText = `\n\n> ${emoji} **Using tool: ${transformedToolName}**\n\n`;

          if (!this.currentResponse) {
            this.currentResponse = "";
          }
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

      case "complete":
        // Handle completion
        this.emit({
          id: message.message_id,
          content: this.currentResponse || "",
          timestamp: new Date().toISOString(),
          sender: "agent",
          type: "message",
        });
        this.currentResponse = ""; // Reset for next message
        this.announcedTools.clear(); // Reset announced tools
        break;

      case "error":
        // Handle errors
        this.emit({
          id: this.messageId++,
          content: `Error: ${message.data.error}`,
          timestamp: new Date().toISOString(),
          sender: "agent",
          type: "message",
        });
        break;

      case "status":
        // Handle status updates (like "processing...")
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

  async sendMessage(content, codebaseDir, outputDir) {
    if (!this.isConnected || !this.websocket) {
      throw new Error("WebSocket not connected");
    }

    const messageId = this.messageId++;

    // Send message to WebSocket server
    const wsMessage = {
      type: "chat",
      message: content,
    };

    this.websocket.send(JSON.stringify(wsMessage));
    return { id: messageId };
  }

  emit(message) {
    this.subscribers.forEach((callback) => callback(message));
  }
}

export const irisService = new IrisService();
