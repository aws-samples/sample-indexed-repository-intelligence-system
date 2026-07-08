// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
/**
 * Utility functions for formatting data in the chat UI
 */

/**
 * Formats an ISO timestamp string into a human-readable format.
 * @param {string} isoTimestamp - ISO 8601 formatted timestamp string
 * @returns {string} Human-readable date/time string
 */
export function formatTimestamp(isoTimestamp) {
  if (!isoTimestamp) {
    return "Unknown";
  }

  const date = new Date(isoTimestamp);

  if (isNaN(date.getTime())) {
    return "Invalid date";
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Formats a byte value into a human-readable file size string.
 * @param {number} bytes - File size in bytes (non-negative integer)
 * @returns {string} Formatted file size string (e.g., "1.5 KB")
 */
export function formatFileSize(bytes) {
  if (typeof bytes !== "number" || bytes < 0 || !Number.isFinite(bytes)) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let unitIndex = 0;
  let size = bytes;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  // For bytes, show whole numbers; for larger units, show up to 2 decimal places
  if (unitIndex === 0) {
    return `${Math.round(size)} ${units[unitIndex]}`;
  }

  return `${size.toFixed(2).replace(/\.?0+$/, "")} ${units[unitIndex]}`;
}
