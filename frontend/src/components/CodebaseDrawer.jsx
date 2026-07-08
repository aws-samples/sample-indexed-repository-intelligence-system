// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useCallback } from "react";
import { ChevronLeft, ChevronRight, Folder, Calendar } from "lucide-react";
import TreeView from "./TreeView";
import { formatTimestamp } from "../utils/formatters";

/**
 * CodebaseDrawer component - displays codebase information in a collapsible side panel
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the drawer is open
 * @param {Function} props.onToggle - Callback to toggle drawer open/close
 * @param {Object} props.codebaseInfo - Codebase information
 * @param {Object} props.treeStructure - File tree structure
 * @param {Function} [props.onFileClick] - Callback when a file is clicked in the tree
 */
const CodebaseDrawer = ({
  isOpen,
  onToggle,
  codebaseInfo,
  treeStructure,
  onFileClick,
}) => {
  const handleToggle = useCallback(() => {
    onToggle();
  }, [onToggle]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onToggle();
      }
    },
    [onToggle],
  );

  // Extract evaluation data from codebaseInfo
  const codebaseDir = codebaseInfo?.codebase_dir.split("/").pop() || "Unknown";
  const lastEvaluation = codebaseInfo?.evaluation?.last_evaluation || null;

  return (
    <div className="relative flex h-full" data-testid="codebase-drawer">
      {/* Toggle Button */}
      <button
        type="button"
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        className={`
          absolute top-4 z-10 flex items-center justify-center
          w-6 h-12 bg-white border border-gray-200 rounded-l-md
          hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500
          transition-all duration-300 ease-in-out shadow-sm
          -left-6
        `}
        aria-label={isOpen ? "Close codebase drawer" : "Open codebase drawer"}
        aria-expanded={isOpen}
        data-testid="drawer-toggle"
      >
        {isOpen ? (
          <ChevronRight className="w-5 h-5" />
        ) : (
          <ChevronLeft className="w-5 h-5" />
        )}
      </button>

      {/* Drawer Panel */}
      <div
        className={`
          h-full bg-white border-l border-gray-200 overflow-hidden
          transition-all duration-300 ease-in-out
          ${isOpen ? "w-80 opacity-100" : "w-0 opacity-0"}
        `}
        aria-hidden={!isOpen}
        data-testid="drawer-panel"
      >
        <div className="h-full flex flex-col p-4 min-w-[320px] max-md:min-w-[280px]">
          {/* Header */}
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            Codebase Analysis
          </h2>

          {/* Codebase Info Section */}
          <div className="space-y-3 mb-4 pb-4 border-b border-gray-200">
            {/* Codebase Directory */}
            <div className="flex items-start gap-2">
              <Folder className="w-4 h-4 text-blue-500 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <span className="text-xs text-gray-500 block">Codebase</span>
                <span
                  className="text-sm text-gray-700 break-all line-clamp-2"
                  title={codebaseDir}
                  data-testid="codebase-path"
                >
                  {codebaseDir}
                </span>
              </div>
            </div>

            {/* Last Evaluation */}
            <div className="flex items-start gap-2">
              <Calendar className="w-4 h-4 text-gray-500 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <span className="text-xs text-gray-500 block">
                  Last Evaluation
                </span>
                <span
                  className="text-sm text-gray-700"
                  data-testid="last-evaluation"
                >
                  {formatTimestamp(lastEvaluation)}
                </span>
              </div>
            </div>
          </div>

          {/* TreeView Section */}
          <div className="flex-1 overflow-hidden">
            {treeStructure ? (
              <TreeView
                treeStructure={treeStructure}
                className="h-full"
                onFileClick={onFileClick}
              />
            ) : (
              <div className="text-sm text-gray-500 p-2">
                No file structure available
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CodebaseDrawer;
