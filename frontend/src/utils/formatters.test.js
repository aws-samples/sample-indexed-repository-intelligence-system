// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { formatTimestamp, formatFileSize } from "./formatters";

describe("formatters", () => {
  /**
   * **Feature: chat-ui-modernization, Property 3: Timestamp formatting produces human-readable output**
   * **Validates: Requirements 3.3**
   *
   * For any valid ISO timestamp string, the formatTimestamp function SHALL return
   * a non-empty string that does not contain the raw ISO format.
   */
  describe("formatTimestamp - Property 3", () => {
    it("should produce human-readable output for any valid ISO timestamp", () => {
      fc.assert(
        fc.property(
          fc.date({
            min: new Date("1970-01-01"),
            max: new Date("2100-12-31"),
            noInvalidDate: true,
          }),
          (date) => {
            // Skip invalid dates
            if (isNaN(date.getTime())) return true;

            const isoString = date.toISOString();
            const result = formatTimestamp(isoString);

            // Result should be a non-empty string
            expect(typeof result).toBe("string");
            expect(result.length).toBeGreaterThan(0);

            // Result should not contain the raw ISO format pattern (YYYY-MM-DDTHH:MM:SS)
            // We check for the ISO date-time separator pattern, not just 'T' (which appears in day names like Thursday)
            expect(result).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
            expect(result).not.toMatch(/\.000Z$/);
          },
        ),
        { numRuns: 100 },
      );
    });
  });

  /**
   * **Feature: chat-ui-modernization, Property 6: File size formatting validity**
   * **Validates: Requirements 4.3**
   *
   * For any non-negative integer byte value, the formatFileSize function SHALL return
   * a string matching the pattern `{number} {unit}` where unit is one of B, KB, MB, or GB.
   */
  describe("formatFileSize - Property 6", () => {
    it("should return valid format for any non-negative integer byte value", () => {
      fc.assert(
        fc.property(fc.nat({ max: Number.MAX_SAFE_INTEGER }), (bytes) => {
          const result = formatFileSize(bytes);

          // Result should be a string
          expect(typeof result).toBe("string");

          // Result should match pattern: number followed by space and unit
          const pattern = /^[\d.]+\s+(B|KB|MB|GB)$/;
          expect(result).toMatch(pattern);

          // Extract the unit and verify it's valid
          const unit = result.split(" ").pop();
          expect(["B", "KB", "MB", "GB"]).toContain(unit);
        }),
        { numRuns: 100 },
      );
    });
  });
});
