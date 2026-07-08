// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { Folder, Calendar, File, Loader2 } from "lucide-react";
import { formatTimestamp } from "../utils/formatters";

/**
 * Loading spinner component
 */
const LoadingSpinner = () => (
  <div className="flex items-center gap-2 text-gray-500">
    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
    <span className="text-sm">Loading evaluation status...</span>
  </div>
);

/**
 * EvaluationStatus component - displays codebase evaluation information
 */
const EvaluationStatus = ({ evaluationData }) => {
  if (!evaluationData) {
    return (
      <div className="p-2">
        <LoadingSpinner />
      </div>
    );
  }

  const { last_evaluation, evaluated_files, evaluation_coverage, codebaseDir } =
    evaluationData;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800 m-0">
          Codebase Analysis
        </h2>
      </div>

      <div className="space-y-2 text-sm">
        {/* Codebase Directory */}
        <div className="flex items-center gap-2 text-gray-600">
          <Folder className="w-4 h-4 text-blue-500 flex-shrink-0" />
          <span>Codebase: {codebaseDir}</span>
        </div>

        {/* Last Evaluation */}
        <div className="flex items-center gap-2 text-gray-600">
          <Calendar className="w-4 h-4 text-gray-500 flex-shrink-0" />
          <span>Last Evaluation: {formatTimestamp(last_evaluation)}</span>
        </div>

        {/* Coverage */}
        {evaluated_files !== undefined && (
          <div className="flex items-center gap-2 text-gray-600">
            <File className="w-4 h-4 text-gray-500 flex-shrink-0" />
            <span>
              Coverage: {evaluation_coverage}% ({evaluated_files} files)
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default EvaluationStatus;
