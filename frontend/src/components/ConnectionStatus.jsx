// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from "react";
import { RefreshCw } from "lucide-react";

/**
 * ConnectionStatus component - Shows connected/disconnected indicator
 */

/**
 * ConnectionStatus component
 * @param {Object} props
 * @param {boolean} props.isConnected - Whether the connection is established
 * @param {string} [props.className] - Additional CSS classes
 * @param {boolean} [props.showLabel] - Whether to show text label (default: true)
 * @param {string} [props.size] - Size variant: 'sm' | 'md' | 'lg'
 * @param {Function} [props.onReconnect] - Callback to trigger reconnection
 * @param {boolean} [props.isReconnecting] - Whether reconnection is in progress
 */
export default function ConnectionStatus({
  isConnected,
  className = "",
  showLabel = true,
  size = "md",
  onReconnect,
  isReconnecting = false,
}) {
  const sizeStyles = {
    sm: {
      dot: "w-2 h-2",
      text: "text-xs",
      gap: "gap-1.5",
      button: "text-xs px-1.5 py-0.5",
    },
    md: {
      dot: "w-2.5 h-2.5",
      text: "text-sm",
      gap: "gap-2",
      button: "text-sm px-2 py-1",
    },
    lg: {
      dot: "w-3 h-3",
      text: "text-base",
      gap: "gap-2.5",
      button: "text-base px-2.5 py-1",
    },
  };

  const styles = sizeStyles[size] || sizeStyles.md;

  const statusConfig = isConnected
    ? {
        dotColor: "bg-green-500",
        textColor: "text-green-700",
        label: "Connected",
        ariaLabel: "Connection status: Connected",
      }
    : {
        dotColor: "bg-red-500",
        textColor: "text-red-700",
        label: isReconnecting ? "Reconnecting..." : "Disconnected",
        ariaLabel: `Connection status: ${isReconnecting ? "Reconnecting" : "Disconnected"}`,
      };

  return (
    <div
      className={`flex items-center ${styles.gap} ${className}`}
      role="status"
      aria-label={statusConfig.ariaLabel}
    >
      <span
        className={`${styles.dot} rounded-full ${statusConfig.dotColor} ${isConnected ? "animate-pulse" : ""} ${isReconnecting ? "animate-pulse" : ""}`}
        aria-hidden="true"
      />
      {showLabel && (
        <span
          className={`${styles.text} font-medium ${statusConfig.textColor}`}
        >
          {statusConfig.label}
        </span>
      )}
      {!isConnected && onReconnect && !isReconnecting && (
        <button
          onClick={onReconnect}
          className={`${styles.button} flex items-center gap-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors`}
          aria-label="Reconnect to server"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Reconnect</span>
        </button>
      )}
      {isReconnecting && (
        <RefreshCw className="w-3.5 h-3.5 text-gray-500 animate-spin" />
      )}
    </div>
  );
}
