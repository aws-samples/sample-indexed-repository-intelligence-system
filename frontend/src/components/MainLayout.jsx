// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useCallback } from "react";

/**
 * MainLayout component - Flex layout with chat panel and drawer
 */

/**
 * MainLayout component
 * @param {Object} props
 * @param {React.ReactNode} props.children - Main content (chat panel)
 * @param {React.ReactNode} props.drawer - Drawer component
 * @param {boolean} [props.drawerOpen] - Controlled drawer state
 * @param {Function} [props.onDrawerToggle] - Callback when drawer is toggled
 * @param {boolean} [props.hasDrawer] - Whether drawer should be shown
 */
export default function MainLayout({
  children,
  drawer,
  drawerOpen: controlledDrawerOpen,
  onDrawerToggle,
  hasDrawer = true,
}) {
  // Internal state for uncontrolled mode
  // Default to closed on mobile, open on desktop
  const [internalDrawerOpen, setInternalDrawerOpen] = useState(() => {
    // Check if we're on mobile (less than 768px)
    if (typeof window !== "undefined") {
      return window.innerWidth >= 768;
    }
    return true;
  });

  // Use controlled or uncontrolled state
  const isControlled = controlledDrawerOpen !== undefined;
  const drawerOpen = isControlled ? controlledDrawerOpen : internalDrawerOpen;

  const handleDrawerToggle = useCallback(() => {
    if (isControlled) {
      onDrawerToggle?.();
    } else {
      setInternalDrawerOpen((prev) => !prev);
    }
  }, [isControlled, onDrawerToggle]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Main Content Area */}
      <main
        className={`
                    flex-1 flex flex-col min-w-0 overflow-hidden
                    transition-all duration-300 ease-in-out
                `}
      >
        {children}
      </main>

      {/* Drawer Area - Hidden on mobile when closed, visible toggle always */}
      {hasDrawer && drawer && (
        <aside
          className={`
                        flex-shrink-0 h-full
                        transition-all duration-300 ease-in-out
                        ${drawerOpen ? "w-80 md:w-80" : "w-0"}
                        ${drawerOpen ? "max-md:absolute max-md:right-0 max-md:top-0 max-md:z-20 max-md:h-full max-md:shadow-drawer" : ""}
                    `}
        >
          {React.isValidElement(drawer)
            ? React.cloneElement(drawer, {
                isOpen: drawerOpen,
                onToggle: handleDrawerToggle,
              })
            : typeof drawer === "function"
              ? drawer({ isOpen: drawerOpen, onToggle: handleDrawerToggle })
              : drawer}
        </aside>
      )}
    </div>
  );
}
