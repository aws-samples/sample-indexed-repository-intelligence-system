// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from "react";
import { XCircle, X } from "lucide-react";

/**
 * ErrorAlert component - Dismissible error alert with icon
 */

/**
 * ErrorAlert component
 * @param {Object} props
 * @param {string} props.message - Error message to display
 * @param {Function} props.onDismiss - Callback when alert is dismissed
 * @param {string} [props.className] - Additional CSS classes
 * @param {string} [props.variant] - Alert variant: 'error' | 'warning' | 'info'
 */
export default function ErrorAlert({
  message,
  onDismiss,
  className = "",
  variant = "error",
}) {
  if (!message) return null;

  const variantStyles = {
    error: {
      container: "bg-red-50 border-red-200",
      icon: "text-red-500",
      text: "text-red-700",
      button: "text-red-500 hover:text-red-700",
    },
    warning: {
      container: "bg-yellow-50 border-yellow-200",
      icon: "text-yellow-500",
      text: "text-yellow-700",
      button: "text-yellow-500 hover:text-yellow-700",
    },
    info: {
      container: "bg-blue-50 border-blue-200",
      icon: "text-blue-500",
      text: "text-blue-700",
      button: "text-blue-500 hover:text-blue-700",
    },
  };

  const styles = variantStyles[variant] || variantStyles.error;

  return (
    <div
      className={`${styles.container} border rounded-lg p-3 flex items-start gap-3 ${className}`}
      role="alert"
      aria-live="assertive"
    >
      <XCircle className={`w-5 h-5 ${styles.icon} flex-shrink-0 mt-0.5`} />
      <p className={`flex-1 text-sm ${styles.text}`}>{message}</p>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className={`${styles.button} transition-colors p-0.5 rounded hover:bg-white/50`}
          aria-label="Dismiss error"
          type="button"
        >
          <X className="w-5 h-5" />
        </button>
      )}
    </div>
  );
}
