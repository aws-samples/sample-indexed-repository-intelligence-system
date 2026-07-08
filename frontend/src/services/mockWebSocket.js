// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
class MockWebSocketService {
  constructor() {
    this.subscribers = new Set();
    this.messageId = 1;
    this.isConnected = false;
  }

  connect() {
    return new Promise((resolve) => {
      setTimeout(() => {
        this.isConnected = true;
        console.log("Mock WebSocket connected");
        resolve();
      }, 500);
    });
  }

  disconnect() {
    this.isConnected = false;
    this.subscribers.clear();
    console.log("Mock WebSocket disconnected");
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  sendMessage(content) {
    if (!this.isConnected) {
      throw new Error("WebSocket not connected");
    }

    const userMessage = {
      id: this.messageId++,
      content,
      timestamp: new Date().toISOString(),
      sender: "user",
      type: "message",
    };

    // Emit user message immediately
    this.emit(userMessage);

    // Simulate agent typing
    setTimeout(() => {
      this.emit({
        id: this.messageId++,
        type: "typing",
        sender: "agent",
        timestamp: new Date().toISOString(),
      });
    }, 500);

    // Emit agent response after delay
    setTimeout(() => {
      const agentMessage = {
        id: this.messageId++,
        content: this.generateAgentResponse(content),
        timestamp: new Date().toISOString(),
        sender: "agent",
        type: "message",
      };
      this.emit(agentMessage);
    }, 2000);

    return userMessage;
  }

  emit(message) {
    this.subscribers.forEach((callback) => callback(message));
  }

  generateAgentResponse(userMessage) {
    const responses = [
      `I understand you mentioned "${userMessage}". Let me help you with that.`,
      `That's an interesting point about "${userMessage}". Could you provide more details?`,
      `Based on your message about "${userMessage}", here are some suggestions...`,
      `I see you're asking about "${userMessage}". Let me analyze this for you.`,
      `Thank you for sharing "${userMessage}". Here's what I think...`,
    ];
    return responses[Math.floor(Math.random() * responses.length)];
  }
}

export const mockWebSocketService = new MockWebSocketService();
