// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useEffect } from "react";
import { AlertTriangle, X } from "lucide-react";
import EvaluationStatus from "./EvaluationStatus";
import TreeView from "./TreeView";

/**
 * Alert component for displaying warnings
 */
const Alert = ({ type = "warning", children, onDismiss }) => {
  const bgColor = type === "warning" ? "bg-amber-50" : "bg-red-50";
  const borderColor =
    type === "warning" ? "border-amber-200" : "border-red-200";

  return (
    <div
      className={`${bgColor} ${borderColor} border rounded-lg p-3 flex items-start gap-3`}
    >
      <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
      <div className="flex-1 text-sm text-gray-700">{children}</div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-amber-500 rounded"
          aria-label="Dismiss alert"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};

/**
 * NavigationPanel component - displays codebase information and tree structure
 */
const NavigationPanel = ({ treeStructure, codebaseInfo }) => {
  const [evaluationData, setEvaluationData] = useState(null);
  const [error, setError] = useState(null);

  // Load evaluation data from props
  useEffect(() => {
    try {
      setError(null);

      if (codebaseInfo && codebaseInfo.evaluation) {
        setEvaluationData({
          ...codebaseInfo.evaluation,
          codebaseDir: codebaseInfo.codebase_dir,
        });
      } else {
        // Fallback for when evaluation data is not available
        setEvaluationData({
          last_evaluation: null,
          evaluated_files: 0,
          evaluation_coverage: 0.0,
        });
      }
    } catch (err) {
      console.error("Error processing evaluation data:", err);
      setError("Failed to load evaluation status");
      // Set fallback data
      setEvaluationData({
        last_evaluation: null,
        evaluated_files: 0,
        evaluation_coverage: 0.0,
      });
    }
  }, [codebaseInfo]);

  return (
    <div className="p-4 space-y-4">
      {error && (
        <Alert type="warning" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <EvaluationStatus evaluationData={evaluationData} />

      {treeStructure && <TreeView treeStructure={treeStructure} />}
    </div>
  );
};

export default NavigationPanel;
