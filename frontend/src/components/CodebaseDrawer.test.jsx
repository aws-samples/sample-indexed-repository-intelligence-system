// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import CodebaseDrawer from "./CodebaseDrawer";

describe("CodebaseDrawer", () => {
  const mockTreeStructure = {
    name: "root",
    type: "directory",
    children: [
      { name: "file1.js", type: "file", size: 1024 },
      { name: "folder1", type: "directory", children: [] },
    ],
  };

  const mockCodebaseInfo = {
    codebase_dir: "/path/to/codebase",
    evaluation: {
      last_evaluation: "2025-01-14T10:30:00Z",
      evaluated_files: 10,
      evaluation_coverage: 85,
    },
  };

  it("renders toggle button", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={false}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const toggleButton = screen.getByTestId("drawer-toggle");
    expect(toggleButton).toBeInTheDocument();
  });

  it("calls onToggle when toggle button is clicked", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={false}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const toggleButton = screen.getByTestId("drawer-toggle");
    fireEvent.click(toggleButton);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("displays codebase name when open", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={true}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const codebasePath = screen.getByTestId("codebase-path");
    expect(codebasePath).toHaveTextContent("codebase");
  });

  it("displays last evaluation timestamp when open", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={true}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const lastEvaluation = screen.getByTestId("last-evaluation");
    expect(lastEvaluation).toBeInTheDocument();
    // Should not show raw ISO format
    expect(lastEvaluation.textContent).not.toContain("2025-01-14T10:30:00Z");
  });

  it("renders TreeView when treeStructure is provided", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={true}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const treeView = screen.getByTestId("tree-view");
    expect(treeView).toBeInTheDocument();
  });

  it("shows fallback message when treeStructure is null", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={true}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={null}
      />,
    );

    expect(screen.getByText("No file structure available")).toBeInTheDocument();
  });

  it("has correct aria-expanded attribute based on isOpen", () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <CodebaseDrawer
        isOpen={false}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const toggleButton = screen.getByTestId("drawer-toggle");
    expect(toggleButton).toHaveAttribute("aria-expanded", "false");

    rerender(
      <CodebaseDrawer
        isOpen={true}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    expect(toggleButton).toHaveAttribute("aria-expanded", "true");
  });

  it("handles keyboard navigation on toggle button", () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={false}
        onToggle={onToggle}
        codebaseInfo={mockCodebaseInfo}
        treeStructure={mockTreeStructure}
      />,
    );

    const toggleButton = screen.getByTestId("drawer-toggle");

    fireEvent.keyDown(toggleButton, { key: "Enter" });
    expect(onToggle).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(toggleButton, { key: " " });
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('displays "Unknown" for missing codebase_dir', () => {
    const onToggle = vi.fn();
    render(
      <CodebaseDrawer
        isOpen={true}
        onToggle={onToggle}
        codebaseInfo={null}
        treeStructure={mockTreeStructure}
      />,
    );

    const codebasePath = screen.getByTestId("codebase-path");
    expect(codebasePath).toHaveTextContent("Unknown");
  });
});
