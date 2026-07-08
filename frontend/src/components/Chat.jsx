// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";
import TypingIndicator from "./TypingIndicator";
import WelcomeScreen, { shouldShowWelcome } from "./WelcomeScreen";
import ErrorAlert from "./ErrorAlert";
import { irisService } from "../services/irisService";

/**
 * Chat component - Main chat interface with messages, input, and streaming support
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 6.3, 6.4, 7.4, 7.5
 * - Message display occupies majority of viewport (1.1)
 * - Streaming response rendering (1.2)
 * - Auto-scroll on new messages (1.3)
 * - Maintain scroll position until new content (1.4)
 * - Display dismissible error alert with error details (6.3)
 * - Notify user on session timeout and disconnect (6.4)
 * - Welcome screen visibility based on messages (7.4)
 * - Restore welcome on conversation clear (7.5)
 */

// Session timeout duration (15 minutes)
const SESSION_TIMEOUT_MS = 15 * 60 * 1000;

export default function Chat({
  config,
  onConnectionChange,
  prefilledInput,
  onPrefilledInputUsed,
}) {
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState(null);
  const [currentResponse, setCurrentResponse] = useState("");
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const inactivityTimeoutRef = useRef(null);
  const userScrolledRef = useRef(false);

  // Reset inactivity timer
  const resetInactivityTimer = () => {
    if (inactivityTimeoutRef.current) {
      clearTimeout(inactivityTimeoutRef.current);
    }
    inactivityTimeoutRef.current = setTimeout(() => {
      setError(
        'Session timed out due to inactivity. Please refresh or click "Reconnect" at the top to reconnect.',
      );
      irisService.disconnect();
      setIsConnected(false);
      onConnectionChange?.(false);
    }, SESSION_TIMEOUT_MS);
  };

  // Update parent when connection status changes
  useEffect(() => {
    onConnectionChange?.(isConnected);
  }, [isConnected, onConnectionChange]);

  // Subscribe to service messages - this subscription persists across reconnects
  useEffect(() => {
    const unsubscribe = irisService.subscribe((message) => {
      resetInactivityTimer();

      if (message.type === "typing") {
        setIsTyping(true);
        setCurrentResponse("");
      } else if (message.type === "partial_message") {
        setCurrentResponse(message.fullContent || message.content);
      } else if (message.type === "message") {
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.id !== message.id);
          return [...filtered, message];
        });
        setIsTyping(false);
        setCurrentResponse("");
      } else if (message.type === "error") {
        // Handle message processing errors (Requirement 6.3)
        setError(
          message.error || "An error occurred while processing your message",
        );
        setIsTyping(false);
        setCurrentResponse("");
      } else if (message.type === "connection_success") {
        setError(null);
        setIsConnected(true);
      } else if (message.type === "connection_lost") {
        // Handle connection lost (Requirement 6.2)
        setError("Connection lost. Attempting to reconnect...");
        setIsConnected(false);
        onConnectionChange?.(false);
      }
    });

    return () => unsubscribe();
  }, [onConnectionChange]);

  // Connect to service on mount
  useEffect(() => {
    const connectService = async () => {
      try {
        await irisService.connect();
        setIsConnected(true);
        setError(null); // Clear any previous connection errors
        resetInactivityTimer();
      } catch (err) {
        // Handle connection errors (Requirement 6.2, 6.3)
        setError(
          "Failed to connect to IRIS service. Please check your connection and try again.",
        );
        setIsConnected(false);
        onConnectionChange?.(false);
      }
    };

    const handleBeforeUnload = () => {
      if (inactivityTimeoutRef.current) {
        clearTimeout(inactivityTimeoutRef.current);
      }
      irisService.disconnect();
    };

    const handleActivity = () => {
      if (isConnected) {
        resetInactivityTimer();
      }
    };

    if (config) {
      connectService();

      window.addEventListener("beforeunload", handleBeforeUnload);
      window.addEventListener("mousemove", handleActivity);
      window.addEventListener("keypress", handleActivity);
      window.addEventListener("click", handleActivity);

      return () => {
        if (inactivityTimeoutRef.current) {
          clearTimeout(inactivityTimeoutRef.current);
        }
        irisService.disconnect();
        window.removeEventListener("beforeunload", handleBeforeUnload);
        window.removeEventListener("mousemove", handleActivity);
        window.removeEventListener("keypress", handleActivity);
        window.removeEventListener("click", handleActivity);
      };
    }
  }, [config]);

  // Auto-scroll to bottom when new messages arrive (unless user scrolled up)
  useEffect(() => {
    // Only auto-scroll if there's agent content (streaming response or agent message)
    const hasAgentContent =
      currentResponse || messages.some((m) => m.sender === "agent");

    if (!userScrolledRef.current && hasAgentContent) {
      // Scroll to bottom without animation to prevent over-scroll effect
      if (messagesContainerRef.current) {
        messagesContainerRef.current.scrollTop =
          messagesContainerRef.current.scrollHeight;
      }
    }
  }, [messages, isTyping, currentResponse]);

  // Track user scroll to maintain position
  const handleScroll = () => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } =
        messagesContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      userScrolledRef.current = !isAtBottom;
    }
  };

  const handleSubmit = async (inputValue) => {
    if (!inputValue.trim() || !isConnected) return;

    // Add user message to the list immediately
    const userMessage = {
      id: Date.now(),
      content: inputValue,
      timestamp: new Date().toISOString(),
      sender: "user",
      type: "message",
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);
    setCurrentResponse("");

    try {
      resetInactivityTimer();
      await irisService.sendMessage(
        inputValue,
        config.codebase_dir,
        config.output_dir,
      );
      setError(null);
    } catch (err) {
      // Handle message send errors (Requirement 6.3)
      const errorMessage =
        err?.message || "Failed to send message. Please try again.";
      setError(errorMessage);
      // Hide typing indicator on error
      setIsTyping(false);
    }
  };

  const handlePromptClick = (promptText) => {
    handleSubmit(promptText);
  };

  const showWelcome = shouldShowWelcome(messages);

  return (
    <div className="flex flex-col h-full">
      {/* Error Alert */}
      <ErrorAlert
        message={error}
        onDismiss={() => setError(null)}
        className="mx-4 mb-4"
      />

      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 pb-24"
      >
        {showWelcome ? (
          <WelcomeScreen onPromptClick={handlePromptClick} />
        ) : (
          <div className="max-w-4xl mx-auto py-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {/* Streaming response */}
            {currentResponse && (
              <MessageBubble
                message={{
                  id: "streaming",
                  content: currentResponse,
                  timestamp: new Date().toISOString(),
                  sender: "agent",
                  type: "streaming",
                }}
                isStreaming={true}
              />
            )}

            {/* Typing indicator */}
            {isTyping && !currentResponse && <TypingIndicator />}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Fixed Chat Input */}
      <ChatInput
        onSubmit={handleSubmit}
        disabled={!isConnected}
        placeholder={
          isConnected
            ? "Ask a question about the codebase..."
            : "Connecting to service..."
        }
        prefilledValue={prefilledInput}
        onPrefilledValueUsed={onPrefilledInputUsed}
      />
    </div>
  );
}
