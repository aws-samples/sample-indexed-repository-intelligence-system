// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { describe, it, expect, vi } from "vitest";
import * as fc from "fast-check";
import { render, screen, fireEvent } from "@testing-library/react";
import WelcomeScreen, { shouldShowWelcome } from "./WelcomeScreen";

/**
 * Arbitrary for generating valid message objects
 */
const messageArb = () =>
  fc.record({
    id: fc.oneof(fc.string({ minLength: 1 }), fc.integer()),
    content: fc.string(),
    // Generate timestamp as integer milliseconds and convert to ISO string
    // Using integer range to avoid invalid date issues
    timestamp: fc
      .integer({ min: 0, max: 4102444800000 })
      .map((ms) => new Date(ms).toISOString()),
    sender: fc.constantFrom("user", "agent"),
    type: fc.constantFrom("message", "partial_message", "streaming"),
  });

/**
 * Arbitrary for generating arrays of messages
 */
const messagesArrayArb = () =>
  fc.array(messageArb(), { minLength: 0, maxLength: 50 });

describe("WelcomeScreen", () => {
  /**
   * **Feature: chat-ui-modernization, Property 7: Welcome visibility based on message count**
   * **Validates: Requirements 7.4**
   *
   * For any messages array, the welcome screen SHALL be visible if and only if
   * the array is empty.
   */
  describe("Property 7: Welcome visibility based on message count", () => {
    it("shouldShowWelcome returns true if and only if messages array is empty", () => {
      fc.assert(
        fc.property(messagesArrayArb(), (messages) => {
          const result = shouldShowWelcome(messages);

          // Welcome should be visible if and only if messages array is empty
          const expectedVisible = messages.length === 0;
          expect(result).toBe(expectedVisible);
        }),
        { numRuns: 100 },
      );
    });

    it("shouldShowWelcome returns true for empty array", () => {
      expect(shouldShowWelcome([])).toBe(true);
    });

    it("shouldShowWelcome returns false for non-empty arrays", () => {
      fc.assert(
        fc.property(
          fc.array(messageArb(), { minLength: 1, maxLength: 50 }),
          (messages) => {
            const result = shouldShowWelcome(messages);
            expect(result).toBe(false);
          },
        ),
        { numRuns: 100 },
      );
    });
  });

  describe("WelcomeScreen rendering", () => {
    it("renders welcome message and example prompts", () => {
      render(<WelcomeScreen onPromptClick={() => {}} />);

      // Check welcome message is displayed
      expect(
        screen.getByText("Welcome to Indexed Repository Intelligence System (IRIS)"),
      ).toBeInTheDocument();

      // Check example prompts are displayed
      expect(
        screen.getByText("What does this codebase do?"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Explain the architecture of this project"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("What are the main files and their purposes?"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("What dependencies does this project use?"),
      ).toBeInTheDocument();
    });

    it("calls onPromptClick when a prompt card is clicked", () => {
      const mockOnPromptClick = vi.fn();
      render(<WelcomeScreen onPromptClick={mockOnPromptClick} />);

      // Click on the first prompt
      const promptButton = screen.getByRole("button", {
        name: /Ask: What does this codebase do\?/i,
      });
      fireEvent.click(promptButton);

      expect(mockOnPromptClick).toHaveBeenCalledWith(
        "What does this codebase do?",
      );
    });

    it("all prompt cards are clickable and trigger onPromptClick", () => {
      const mockOnPromptClick = vi.fn();
      render(<WelcomeScreen onPromptClick={mockOnPromptClick} />);

      const promptButtons = screen.getAllByRole("button");

      promptButtons.forEach((button) => {
        fireEvent.click(button);
      });

      // Should have been called once for each prompt
      expect(mockOnPromptClick).toHaveBeenCalledTimes(4);
    });
  });
});
