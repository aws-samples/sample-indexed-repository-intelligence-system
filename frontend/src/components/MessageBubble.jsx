// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Bot, User } from "lucide-react";
import CodeBlock from "./CodeBlock";

/**
 * MessageBubble component - Displays chat messages with distinct styling
 */

/**
 * @typedef {Object} Message
 * @property {string|number} id - Unique message identifier
 * @property {string} content - Message content
 * @property {string} timestamp - ISO timestamp
 * @property {'user'|'agent'} sender - Message sender type
 * @property {'message'|'partial_message'|'streaming'} type - Message type
 */

/**
 * AI Avatar component
 */
function AIAvatar({ isStreaming }) {
  return (
    <div
      className={`
            w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0
            ${isStreaming ? "bg-purple-100 animate-pulse" : "bg-purple-600"}
        `}
    >
      <Bot
        className={`w-5 h-5 ${isStreaming ? "text-purple-600" : "text-white"}`}
      />
    </div>
  );
}

/**
 * User Avatar component
 */
function UserAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
      <User className="w-5 h-5 text-white" />
    </div>
  );
}

/**
 * Streaming indicator dots
 */
function StreamingIndicator() {
  return (
    <div className="flex items-center gap-1 mt-4">
      <span
        className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"
        style={{ animationDelay: "0ms" }}
      />
      <span
        className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"
        style={{ animationDelay: "150ms" }}
      />
      <span
        className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"
        style={{ animationDelay: "300ms" }}
      />
    </div>
  );
}

const MessageBubble = React.memo(({ message, isStreaming = false }) => {
  const isUser = message.sender === "user";

  // Memoize the ReactMarkdown configuration
  const markdownComponents = useMemo(
    () => ({
      code: CodeBlock,
    }),
    [],
  );

  const remarkPlugins = useMemo(() => [remarkGfm], []);

  if (isUser) {
    // User message - right aligned
    return (
      <div className="flex justify-end gap-3 mb-4">
        <div className="max-w-[100%] bg-blue-600 text-white rounded-2xl rounded-tr-md px-4 py-3 shadow-sm">
          <div className="whitespace-pre-wrap break-words">
            {message.content}
          </div>
        </div>
        <UserAvatar />
      </div>
    );
  }

  // AI message - left aligned
  return (
    <div className="flex justify-start gap-3 mb-4">
      <AIAvatar isStreaming={isStreaming} />
      <div className="max-w-[100%] bg-gray-100 text-gray-900 rounded-2xl rounded-tl-md px-4 py-3 shadow-sm">
        <div className="message-content">
          {/* SECURITY: skipHtml={true} prevents XSS from AI-generated HTML.
              Do NOT remove this prop without adding an alternative sanitizer. */}
          <ReactMarkdown
            remarkPlugins={remarkPlugins}
            components={markdownComponents}
            skipHtml={true}
          >
            {String(message.content)}
          </ReactMarkdown>
        </div>
        {isStreaming && <StreamingIndicator />}
      </div>
    </div>
  );
});

MessageBubble.displayName = "MessageBubble";

export default MessageBubble;
