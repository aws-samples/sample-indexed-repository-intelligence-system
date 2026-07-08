// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useCallback, useMemo } from "react";
import {
  Folder,
  FolderOpen,
  File,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";
import { formatFileSize } from "../utils/formatters";

/**
 * Generates a unique node ID based on the path from root
 * @param {string} parentPath - Parent node path
 * @param {string} name - Current node name
 * @returns {string} Unique node identifier
 */
export const getNodeId = (parentPath, name) => {
  return parentPath ? `${parentPath}/${name}` : name;
};

/**
 * Collects all folder node IDs from a tree structure
 * @param {Object} node - Tree node
 * @param {string} parentPath - Parent path for ID generation
 * @returns {Set<string>} Set of all folder node IDs
 */
export const collectAllFolderIds = (node, parentPath = "") => {
  const ids = new Set();
  if (!node) return ids;

  const nodeId = getNodeId(parentPath, node.name);

  if (node.type === "directory" && node.children && node.children.length > 0) {
    ids.add(nodeId);
    node.children.forEach((child) => {
      const childIds = collectAllFolderIds(child, nodeId);
      childIds.forEach((id) => ids.add(id));
    });
  }

  return ids;
};

/**
 * TreeNode component - renders a single node in the tree (file or folder)
 * Recursively renders children for directory nodes
 */
export const TreeNode = ({
  node,
  level = 0,
  onToggle,
  onFileClick,
  expandedNodes,
  parentPath = "",
}) => {
  const isDirectory = node.type === "directory";
  const hasChildren = isDirectory && node.children && node.children.length > 0;
  const nodeId = getNodeId(parentPath, node.name);
  const isExpanded = expandedNodes.has(nodeId);

  const handleClick = useCallback(() => {
    if (isDirectory && hasChildren) {
      onToggle(nodeId);
    } else if (!isDirectory && onFileClick) {
      // For files, trigger the file click callback with the full path
      onFileClick(nodeId);
    }
  }, [isDirectory, hasChildren, nodeId, onToggle, onFileClick]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleClick();
      }
    },
    [handleClick],
  );

  const indentStyle = { paddingLeft: `${level * 16}px` };

  return (
    <div className="tree-node" data-testid={`tree-node-${nodeId}`}>
      <div
        className={`flex items-center py-1 px-2 hover:bg-gray-100 rounded transition-colors duration-150 cursor-pointer ${
          isDirectory
            ? "font-medium text-gray-800"
            : "text-gray-600 hover:text-blue-600"
        }`}
        style={indentStyle}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-expanded={hasChildren ? isExpanded : undefined}
        aria-label={
          isDirectory
            ? `${node.name} folder, ${isExpanded ? "expanded" : "collapsed"}`
            : `${node.name} file, click to ask about this file`
        }
      >
        <div className="flex items-center flex-1 gap-1.5 min-w-0">
          {/* Toggle chevron for folders with children */}
          {hasChildren ? (
            <ChevronRight
              className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
              aria-hidden="true"
            />
          ) : (
            <span className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
          )}

          {/* Folder or file icon */}
          {isDirectory ? (
            isExpanded ? (
              <FolderOpen
                className="w-4 h-4 text-blue-500 flex-shrink-0"
                aria-hidden="true"
              />
            ) : (
              <Folder
                className="w-4 h-4 text-blue-500 flex-shrink-0"
                aria-hidden="true"
              />
            )
          ) : (
            <File
              className="w-4 h-4 text-gray-400 flex-shrink-0"
              aria-hidden="true"
            />
          )}

          {/* Node name */}
          <span className="truncate text-sm">{node.name}</span>

          {/* File size for files */}
          {!isDirectory && node.size !== undefined && (
            <span className="ml-auto text-xs text-gray-400 flex-shrink-0 pl-2">
              {formatFileSize(node.size)}
            </span>
          )}
        </div>

        {/* Error indicator */}
        {node.error && (
          <div className="flex items-center gap-1 ml-2 text-red-500 text-xs">
            <AlertTriangle
              className="w-4 h-4 flex-shrink-0"
              aria-hidden="true"
            />
            <span>{node.error}</span>
          </div>
        )}
      </div>

      {/* Children (rendered when expanded) */}
      {hasChildren && isExpanded && (
        <div className="tree-children animate-slideDown">
          {node.children.map((child, index) => (
            <TreeNode
              key={`${child.name}-${index}`}
              node={child}
              level={level + 1}
              onToggle={onToggle}
              onFileClick={onFileClick}
              expandedNodes={expandedNodes}
              parentPath={nodeId}
            />
          ))}
        </div>
      )}
    </div>
  );
};

/**
 * Toggles a folder's expanded state
 * @param {Set<string>} expandedNodes - Current set of expanded node IDs
 * @param {string} nodeId - Node ID to toggle
 * @returns {Set<string>} New set with toggled state
 */
export const toggleFolderState = (expandedNodes, nodeId) => {
  const newSet = new Set(expandedNodes);
  if (newSet.has(nodeId)) {
    newSet.delete(nodeId);
  } else {
    newSet.add(nodeId);
  }
  return newSet;
};

/**
 * TreeView component - displays a hierarchical file/folder structure
 * with expand/collapse functionality
 * @param {Object} props
 * @param {Object} props.treeStructure - The tree data structure
 * @param {string} [props.className] - Additional CSS classes
 * @param {Function} [props.onFileClick] - Callback when a file is clicked, receives file path
 */
const TreeView = ({ treeStructure, className = "", onFileClick }) => {
  // Initialize with root node expanded
  const [expandedNodes, setExpandedNodes] = useState(() => {
    if (treeStructure?.name) {
      return new Set([treeStructure.name]);
    }
    return new Set();
  });

  const handleToggle = useCallback((nodeId) => {
    setExpandedNodes((prev) => toggleFolderState(prev, nodeId));
  }, []);

  const handleExpandAll = useCallback(() => {
    if (treeStructure) {
      const allFolderIds = collectAllFolderIds(treeStructure);
      setExpandedNodes(allFolderIds);
    }
  }, [treeStructure]);

  const handleCollapseAll = useCallback(() => {
    setExpandedNodes(new Set());
  }, []);

  // Memoize the tree content to avoid unnecessary re-renders
  const treeContent = useMemo(() => {
    if (!treeStructure) {
      return null;
    }
    return (
      <TreeNode
        node={treeStructure}
        level={0}
        onToggle={handleToggle}
        onFileClick={onFileClick}
        expandedNodes={expandedNodes}
        parentPath=""
      />
    );
  }, [treeStructure, handleToggle, onFileClick, expandedNodes]);

  if (!treeStructure) {
    return (
      <div className="p-4 text-gray-500 text-sm">
        No tree structure available
      </div>
    );
  }

  return (
    <div className={`tree-view ${className}`} data-testid="tree-view">
      {/* Header */}
      <h2 className="text-sm font-semibold text-gray-700 mb-2">
        Current File Tree
      </h2>

      {/* Controls */}
      <div className="flex gap-2 pb-2 mb-2 border-b border-gray-200">
        <button
          type="button"
          onClick={handleExpandAll}
          className="text-xs text-blue-600 hover:text-blue-800 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded px-1"
          aria-label="Expand all directories"
        >
          Expand All
        </button>
        <button
          type="button"
          onClick={handleCollapseAll}
          className="text-xs text-blue-600 hover:text-blue-800 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 rounded px-1"
          aria-label="Collapse all directories"
        >
          Collapse All
        </button>
      </div>

      {/* Tree content */}
      <div className="tree-content max-h-full overflow-y-auto pb-36">
        {treeContent}
      </div>
    </div>
  );
};

export default TreeView;
