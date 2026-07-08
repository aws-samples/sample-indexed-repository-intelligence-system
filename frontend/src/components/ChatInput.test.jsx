// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { describe, it, expect, vi } from "vitest";
import * as fc from "fast-check";
import { render, screen, fireEvent } from "@testing-library/react";
import ChatInput, { isValidMessage } from "./ChatInput";

// Helper to generate whitespace-only strings
const whitespaceArb = () =>
  fc
    .array(fc.constantFrom(" ", "\t", "\n", "\r", "\f", "\v"), {
      minLength: 0,
      maxLength: 20,
    })
    .map((chars) => chars.join(""));

const nonEmptyWhitespaceArb = () =>
  fc
    .array(fc.constantFrom(" ", "\t", "\n", "\r"), {
      minLength: 1,
      maxLength: 20,
    })
    .map((chars) => chars.join(""));

describe("ChatInput", () => {
  /**
   * **Feature: chat-ui-modernization, Property 2: Whitespace-only messages are rejected**
   * **Validates: Requirements 2.4**
   *
   * For any string composed entirely of whitespace characters (spaces, tabs, newlines),
   * attempting to submit it SHALL not add any message to the messages array and SHALL
   * not trigger a WebSocket send.
   */
  describe("Property 2: Whitespace-only messages are rejected", () => {
    it("isValidMessage should return false for any whitespace-only string", () => {
      fc.assert(
        fc.property(whitespaceArb(), (whitespaceString) => {
          const result = isValidMessage(whitespaceString);
          expect(result).toBe(false);
        }),
        { numRuns: 100 },
      );
    });

    it("should not call onSubmit when submitting whitespace-only input", () => {
      fc.assert(
        fc.property(nonEmptyWhitespaceArb(), (whitespaceString) => {
          const mockOnSubmit = vi.fn();
          const { unmount } = render(
            <ChatInput onSubmit={mockOnSubmit} disabled={false} />,
          );

          const input = screen.getByRole("textbox");
          const button = screen.getByRole("button", { name: /send/i });

          // Set the whitespace value
          fireEvent.change(input, { target: { value: whitespaceString } });

          // Try to submit via button click
          fireEvent.click(button);

          // onSubmit should not have been called
          expect(mockOnSubmit).not.toHaveBeenCalled();

          unmount();
        }),
        { numRuns: 100 },
      );
    });

    it("should not call onSubmit when pressing Enter with whitespace-only input", () => {
      fc.assert(
        fc.property(nonEmptyWhitespaceArb(), (whitespaceString) => {
          const mockOnSubmit = vi.fn();
          const { unmount } = render(
            <ChatInput onSubmit={mockOnSubmit} disabled={false} />,
          );

          const input = screen.getByRole("textbox");

          // Set the whitespace value
          fireEvent.change(input, { target: { value: whitespaceString } });

          // Try to submit via Enter key
          fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

          // onSubmit should not have been called
          expect(mockOnSubmit).not.toHaveBeenCalled();

          unmount();
        }),
        { numRuns: 100 },
      );
    });
  });

  describe("Valid message submission", () => {
    it("should call onSubmit with valid non-whitespace messages", () => {
      // Arbitrary for non-empty strings with at least one non-whitespace char
      const validMessageArb = fc
        .string({ minLength: 1 })
        .filter((s) => s.trim().length > 0);

      fc.assert(
        fc.property(validMessageArb, (validMessage) => {
          const mockOnSubmit = vi.fn();
          const { unmount } = render(
            <ChatInput onSubmit={mockOnSubmit} disabled={false} />,
          );

          const input = screen.getByRole("textbox");
          const button = screen.getByRole("button", { name: /send/i });

          // Set the valid value
          fireEvent.change(input, { target: { value: validMessage } });

          // Submit via button click
          fireEvent.click(button);

          // onSubmit should have been called with the message
          expect(mockOnSubmit).toHaveBeenCalledWith(validMessage);

          unmount();
        }),
        { numRuns: 100 },
      );
    });
  });
});
