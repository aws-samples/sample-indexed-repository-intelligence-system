// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from "react";
import { BookOpen, LayoutGrid, FolderOpen, Box, Bot } from "lucide-react";

/**
 * WelcomeScreen component - Displays welcome message and example prompts
 */

/**
 * @typedef {Object} ExamplePrompt
 * @property {string} id - Unique prompt identifier
 * @property {string} text - The prompt text
 * @property {string} icon - Icon type for the prompt
 */

/** @type {ExamplePrompt[]} */
const EXAMPLE_PROMPTS = [
  {
    id: "overview",
    text: "What does this codebase do?",
    icon: "overview",
  },
  {
    id: "architecture",
    text: "Explain the architecture of this project",
    icon: "architecture",
  },
  {
    id: "files",
    text: "What are the main files and their purposes?",
    icon: "files",
  },
  {
    id: "dependencies",
    text: "What dependencies does this project use?",
    icon: "dependencies",
  },
];

/**
 * Icon component for prompt cards
 */
function PromptIcon({ type }) {
  const iconMap = {
    overview: BookOpen,
    architecture: LayoutGrid,
    files: FolderOpen,
    dependencies: Box,
  };

  const IconComponent = iconMap[type] || BookOpen;
  return <IconComponent className="w-5 h-5" />;
}

/**
 * Determines if the welcome screen should be visible
 * @param {Array} messages - Array of chat messages
 * @returns {boolean} True if welcome should be shown (messages array is empty)
 */
export function shouldShowWelcome(messages) {
  return Array.isArray(messages) && messages.length === 0;
}

/**
 * WelcomeScreen component
 * @param {Object} props
 * @param {(prompt: string) => void} props.onPromptClick - Callback when a prompt is clicked
 */
export default function WelcomeScreen({ onPromptClick }) {
  const handlePromptClick = (promptText) => {
    if (onPromptClick) {
      onPromptClick(promptText);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-full px-4 py-6 md:py-8">
      {/* Welcome Message */}
      <div className="text-center mb-6 md:mb-8 max-w-2xl">
        <div className="w-14 h-14 md:w-16 md:h-16 mx-auto mb-3 md:mb-4 bg-purple-100 rounded-full flex items-center justify-center">
          <Bot className="w-7 h-7 md:w-8 md:h-8 text-purple-600" />
        </div>
        <h1 className="text-xl md:text-2xl font-semibold text-gray-900 mb-2">
          Welcome to Indexed Repository Intelligence System (IRIS)
        </h1>
        <p className="text-sm md:text-base text-gray-600">
          I'm your AI assistant for understanding and navigating codebases. Ask
          me anything about the code, architecture, or how things work together.
        </p>
      </div>

      {/* Example Prompts */}
      <div className="w-full max-w-2xl">
        <p className="text-xs md:text-sm text-gray-500 mb-3 text-center">
          Try one of these prompts to get started:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 md:gap-3">
          {EXAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt.id}
              onClick={() => handlePromptClick(prompt.text)}
              className="flex items-center gap-2 md:gap-3 p-3 md:p-4 text-left bg-white border border-gray-200 rounded-lg hover:border-purple-300 hover:bg-purple-50 transition-colors group"
              aria-label={`Ask: ${prompt.text}`}
            >
              <div className="flex-shrink-0 w-9 h-9 md:w-10 md:h-10 bg-gray-100 rounded-lg flex items-center justify-center text-gray-600 group-hover:bg-purple-100 group-hover:text-purple-600 transition-colors">
                <PromptIcon type={prompt.icon} />
              </div>
              <span className="text-xs md:text-sm text-gray-700 group-hover:text-gray-900">
                {prompt.text}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
