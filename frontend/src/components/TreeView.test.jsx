// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { describe, it, expect, vi } from "vitest";
import * as fc from "fast-check";
import { render, screen, fireEvent, within } from "@testing-library/react";
import TreeView, {
  TreeNode,
  getNodeId,
  collectAllFolderIds,
  toggleFolderState,
} from "./TreeView";

/**
 * Arbitrary for generating valid tree node names
 * - Non-empty after trimming
 * - No path separators (/)
 * - No special characters that break CSS selectors (", ', [, ], etc.)
 */
const nodeNameArb = () =>
  fc.stringMatching(/^[a-zA-Z0-9_.-]+$/, { minLength: 1, maxLength: 20 });

/**
 * Arbitrary for generating a file node
 */
const fileNodeArb = () =>
  fc.record({
    name: nodeNameArb(),
    type: fc.constant("file"),
    size: fc.nat({ max: 1000000000 }), // Up to ~1GB
  });

/**
 * Arbitrary for generating a tree structure (recursive)
 * Uses fc.letrec for recursive structure generation
 */
const treeNodeArb = () =>
  fc.letrec((tie) => ({
    tree: fc.oneof(
      { weight: 3, arbitrary: fileNodeArb() },
      {
        weight: 1,
        arbitrary: fc.record({
          name: nodeNameArb(),
          type: fc.constant("directory"),
          children: fc.array(tie("tree"), { minLength: 0, maxLength: 5 }),
        }),
      },
    ),
  })).tree;

/**
 * Arbitrary for generating a directory node (root must be a directory)
 */
const directoryNodeArb = () =>
  fc.record({
    name: nodeNameArb(),
    type: fc.constant("directory"),
    children: fc.array(treeNodeArb(), { minLength: 0, maxLength: 5 }),
  });

/**
 * Counts all nodes in a tree structure
 */
const countAllNodes = (node) => {
  if (!node) return 0;
  let count = 1;
  if (node.children) {
    node.children.forEach((child) => {
      count += countAllNodes(child);
    });
  }
  return count;
};

/**
 * Collects all node names from a tree structure
 */
const collectAllNodeNames = (node, names = new Set()) => {
  if (!node) return names;
  names.add(node.name);
  if (node.children) {
    node.children.forEach((child) => collectAllNodeNames(child, names));
  }
  return names;
};

describe("TreeView", () => {
  /**
   * **Feature: chat-ui-modernization, Property 4: Tree structure rendering completeness**
   * **Validates: Requirements 4.1**
   *
   * For any valid tree structure, the rendered TreeView SHALL contain a node element
   * for every file and directory in the input structure.
   */
  describe("Property 4: Tree structure rendering completeness", () => {
    it("should render all nodes when tree is fully expanded", () => {
      fc.assert(
        fc.property(directoryNodeArb(), (treeStructure) => {
          // Get all folder IDs to expand everything
          const allFolderIds = collectAllFolderIds(treeStructure);

          const { container, unmount } = render(
            <TreeView treeStructure={treeStructure} />,
          );

          // Click "Expand All" to show all nodes
          const expandAllButton = screen.getByRole("button", {
            name: /expand all/i,
          });
          fireEvent.click(expandAllButton);

          // Count rendered tree nodes
          const renderedNodes = container.querySelectorAll(".tree-node");
          const expectedNodeCount = countAllNodes(treeStructure);

          // All nodes should be rendered
          expect(renderedNodes.length).toBe(expectedNodeCount);

          unmount();
        }),
        { numRuns: 100 },
      );
    });

    it("should render all node names when fully expanded", () => {
      fc.assert(
        fc.property(directoryNodeArb(), (treeStructure) => {
          const { container, unmount } = render(
            <TreeView treeStructure={treeStructure} />,
          );

          // Click "Expand All" to show all nodes
          const expandAllButton = screen.getByRole("button", {
            name: /expand all/i,
          });
          fireEvent.click(expandAllButton);

          // Get all expected node names
          const expectedNames = collectAllNodeNames(treeStructure);

          // Check that each name appears in the rendered output
          expectedNames.forEach((name) => {
            const nodeElements = container.querySelectorAll(".tree-node");
            const foundNode = Array.from(nodeElements).some((el) =>
              el.textContent.includes(name),
            );
            expect(foundNode).toBe(true);
          });

          unmount();
        }),
        { numRuns: 100 },
      );
    });
  });
});

/**
 * **Feature: chat-ui-modernization, Property 5: Folder toggle state inversion**
 * **Validates: Requirements 4.2**
 *
 * For any folder node in the tree, clicking the toggle SHALL invert its expanded state
 * (expanded becomes collapsed, collapsed becomes expanded).
 */
describe("Property 5: Folder toggle state inversion", () => {
  it("toggleFolderState should invert the expanded state for any node ID", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }),
        fc.boolean(),
        (nodeId, initiallyExpanded) => {
          // Create initial state
          const initialSet = initiallyExpanded ? new Set([nodeId]) : new Set();

          // Toggle once
          const afterFirstToggle = toggleFolderState(initialSet, nodeId);

          // State should be inverted
          expect(afterFirstToggle.has(nodeId)).toBe(!initiallyExpanded);

          // Toggle again
          const afterSecondToggle = toggleFolderState(afterFirstToggle, nodeId);

          // State should be back to original
          expect(afterSecondToggle.has(nodeId)).toBe(initiallyExpanded);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("clicking a folder should toggle its expanded state", () => {
    fc.assert(
      fc.property(
        directoryNodeArb().filter(
          (node) => node.children && node.children.length > 0,
        ),
        (treeStructure) => {
          const { container, unmount } = render(
            <TreeView treeStructure={treeStructure} />,
          );

          // Find the root folder node (should be expanded by default)
          const rootNodeId = treeStructure.name;
          const rootNode = container.querySelector(
            `[data-testid="tree-node-${rootNodeId}"]`,
          );

          expect(rootNode).toBeTruthy();

          // Get the clickable area (first child div)
          const clickableArea = rootNode.querySelector("div");

          // Initially expanded - children should be visible
          const initialChildCount =
            container.querySelectorAll(".tree-node").length;

          // Click to collapse
          fireEvent.click(clickableArea);

          // After collapse, only root should be visible
          const afterCollapseCount =
            container.querySelectorAll(".tree-node").length;
          expect(afterCollapseCount).toBe(1);

          // Click to expand again
          fireEvent.click(clickableArea);

          // After expand, children should be visible again
          const afterExpandCount =
            container.querySelectorAll(".tree-node").length;
          expect(afterExpandCount).toBe(initialChildCount);

          unmount();
        },
      ),
      { numRuns: 100 },
    );
  });
});

describe("TreeView expand/collapse all", () => {
  const sampleTree = {
    name: "root",
    type: "directory",
    children: [
      {
        name: "src",
        type: "directory",
        children: [
          { name: "index.js", type: "file", size: 1024 },
          { name: "app.js", type: "file", size: 2048 },
        ],
      },
      {
        name: "docs",
        type: "directory",
        children: [{ name: "readme.md", type: "file", size: 512 }],
      },
      { name: "package.json", type: "file", size: 256 },
    ],
  };

  it("should expand all folders when clicking Expand All", () => {
    const { container } = render(<TreeView treeStructure={sampleTree} />);

    // Click Expand All
    const expandAllButton = screen.getByRole("button", { name: /expand all/i });
    fireEvent.click(expandAllButton);

    // All nodes should be visible (root + src + 2 files + docs + 1 file + package.json = 7)
    const allNodes = container.querySelectorAll(".tree-node");
    expect(allNodes.length).toBe(7);
  });

  it("should collapse all folders when clicking Collapse All", () => {
    const { container } = render(<TreeView treeStructure={sampleTree} />);

    // First expand all
    const expandAllButton = screen.getByRole("button", { name: /expand all/i });
    fireEvent.click(expandAllButton);

    // Then collapse all
    const collapseAllButton = screen.getByRole("button", {
      name: /collapse all/i,
    });
    fireEvent.click(collapseAllButton);

    // Only root should be visible
    const allNodes = container.querySelectorAll(".tree-node");
    expect(allNodes.length).toBe(1);
  });

  it("should show root expanded by default", () => {
    const { container } = render(<TreeView treeStructure={sampleTree} />);

    // Root + immediate children should be visible (root + src + docs + package.json = 4)
    const allNodes = container.querySelectorAll(".tree-node");
    expect(allNodes.length).toBe(4);
  });

  it('should display "No tree structure available" when treeStructure is null', () => {
    render(<TreeView treeStructure={null} />);
    expect(screen.getByText("No tree structure available")).toBeInTheDocument();
  });
});
