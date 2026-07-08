// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from "react";
import { Bot } from "lucide-react";

/**
 * TypingIndicator component - Shows when AI is processing but hasn't started streaming
 */

/**
 * AI Avatar component (matches MessageBubble styling)
 */
function AIAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0 animate-pulse">
      <Bot className="w-5 h-5 text-purple-600" />
    </div>
  );
}

/**
 * Animated typing dots
 */
function TypingDots() {
  return (
    <div
      className="flex items-center gap-1.5"
      role="status"
      aria-label="AI is typing"
    >
      <span
        className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce"
        style={{ animationDelay: "0ms", animationDuration: "600ms" }}
      />
      <span
        className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce"
        style={{ animationDelay: "150ms", animationDuration: "600ms" }}
      />
      <span
        className="w-2.5 h-2.5 bg-purple-400 rounded-full animate-bounce"
        style={{ animationDelay: "300ms", animationDuration: "600ms" }}
      />
    </div>
  );
}

export default function TypingIndicator() {
  return (
    <div className="flex justify-start gap-3 mb-4" aria-live="polite">
      <AIAvatar />
      <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
        <TypingDots />
        <span className="sr-only">Generating a response</span>
      </div>
    </div>
  );
}
