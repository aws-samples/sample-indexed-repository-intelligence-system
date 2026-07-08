// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useRef, useEffect } from "react";
import { ChevronDown, Radar } from "lucide-react";
import ConnectionStatus from "./ConnectionStatus";

/**
 * Header component - Custom app header with connection status and user menu
 */

/**
 * User menu dropdown component
 */
function UserMenu({ user, onSignOut }) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const displayName = user?.email || user?.signInDetails?.loginId || "User";

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-100 transition-colors"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        {/* User avatar */}
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
          <span className="text-white text-sm font-medium">
            {displayName.charAt(0).toUpperCase()}
          </span>
        </div>
        <span className="text-sm text-gray-700 hidden sm:block">
          {displayName}
        </span>
        <ChevronDown
          className={`w-4 h-4 text-gray-500 transition-transform ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50">
          <div className="px-4 py-2 border-b border-gray-100">
            <p className="text-sm font-medium text-gray-900 truncate">
              {displayName}
            </p>
          </div>
          <button
            onClick={() => {
              setIsOpen(false);
              onSignOut?.();
            }}
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Logo/Brand icon component
 */
function LogoIcon() {
  return <Radar className="w-8 h-8 text-purple-600" />;
}

/**
 * Header component
 * @param {Object} props
 * @param {string} props.appName - Application name to display
 * @param {boolean} props.isConnected - WebSocket connection status
 * @param {Object} [props.user] - Authenticated user object
 * @param {Function} [props.onSignOut] - Sign out callback
 * @param {boolean} [props.showUserMenu] - Whether to show user menu (auth enabled)
 * @param {Function} [props.onReconnect] - Callback to trigger reconnection
 * @param {boolean} [props.isReconnecting] - Whether reconnection is in progress
 */
export default function Header({
  appName,
  isConnected,
  user,
  onSignOut,
  showUserMenu = false,
  onReconnect,
  isReconnecting = false,
}) {
  return (
    <header className="bg-white border-b border-gray-200 px-3 md:px-4 py-2 md:py-3 shadow-sm">
      <div className="flex items-center justify-between">
        {/* Left: Logo and App Name */}
        <div className="flex items-center gap-2 md:gap-3">
          <LogoIcon />
          <h1 className="text-lg md:text-xl font-semibold text-gray-900 truncate max-w-[150px] sm:max-w-none">
            {appName}
          </h1>
        </div>

        {/* Right: Connection Status and User Menu */}
        <div className="flex items-center gap-2 md:gap-4">
          <ConnectionStatus
            isConnected={isConnected}
            onReconnect={onReconnect}
            isReconnecting={isReconnecting}
          />

          {showUserMenu && user && (
            <UserMenu user={user} onSignOut={onSignOut} />
          )}
        </div>
      </div>
    </header>
  );
}

export { UserMenu };
