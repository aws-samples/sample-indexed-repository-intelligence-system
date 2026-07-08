// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useCallback, useEffect } from "react";
import { Send } from "lucide-react";

/**
 * ChatInput component - Fixed bottom chat input with send button
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4
 * - Fixed at bottom of viewport (2.1)
 * - Enter key submission with input clearing (2.2)
 * - Disabled state when disconnected (2.3)
 * - Whitespace validation to prevent empty submissions (2.4)
 */

/**
 * Validates that the input is not empty or whitespace-only
 * @param {string} value - The input value to validate
 * @returns {boolean} True if valid (non-empty, non-whitespace), false otherwise
 */
export function isValidMessage(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export default function ChatInput({
  onSubmit,
  disabled = false,
  placeholder = "Ask a question about the codebase...",
  prefilledValue = "",
  onPrefilledValueUsed,
}) {
  const [inputValue, setInputValue] = useState("");

  // Handle prefilled value from file clicks
  useEffect(() => {
    if (prefilledValue && prefilledValue.trim()) {
      setInputValue(prefilledValue);
      // Notify parent that the prefilled value has been used
      onPrefilledValueUsed?.();
    }
  }, [prefilledValue, onPrefilledValueUsed]);

  const handleSubmit = useCallback(() => {
    if (!isValidMessage(inputValue) || disabled) {
      return;
    }

    onSubmit(inputValue);
    setInputValue("");
  }, [inputValue, disabled, onSubmit]);

  const handleKeyDown = useCallback(
    (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleChange = useCallback((event) => {
    setInputValue(event.target.value);
  }, []);

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4 md:p-4 shadow-lg z-10">
      <div className="max-w-4xl mx-auto flex gap-2 md:gap-3">
        <input
          type="text"
          value={inputValue}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          aria-label="Chat message input"
          className={`
                        flex-1 px-3 md:px-4 py-2.5 md:py-3 rounded-lg border transition-colors
                        text-base
                        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                        ${
                          disabled
                            ? "bg-gray-100 border-gray-300 text-gray-500 cursor-not-allowed"
                            : "bg-white border-gray-300 hover:border-gray-400"
                        }
                    `}
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !isValidMessage(inputValue)}
          aria-label="Send message"
          className={`
                        px-4 md:px-6 py-2.5 md:py-3 rounded-lg font-medium transition-colors
                        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                        flex-shrink-0
                        ${
                          disabled || !isValidMessage(inputValue)
                            ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                            : "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800"
                        }
                    `}
        >
          <Send className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
