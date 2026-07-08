// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useEffect, useRef, useState, memo } from "react";
import { Loader2, XCircle } from "lucide-react";
import mermaid from "mermaid";
import DOMPurify from "dompurify";

// LLM-generated diagrams are untrusted: 'strict' disables raw HTML/click handlers,
// and DOMPurify is applied to the rendered SVG before injection.
mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  securityLevel: "strict",
  fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
});

// Counter for unique IDs
let mermaidIdCounter = 0;

/**
 * MermaidChart component - renders Mermaid diagrams from code
 */
const MermaidChart = memo(({ chart }) => {
  const containerRef = useRef(null);
  const [svg, setSvg] = useState("");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const idRef = useRef(`mermaid-${++mermaidIdCounter}`);

  useEffect(() => {
    const renderChart = async () => {
      if (!chart || !containerRef.current) return;

      setIsLoading(true);
      setError(null);

      try {
        // Validate the chart syntax first
        await mermaid.parse(chart);

        // Render the chart
        const { svg: renderedSvg } = await mermaid.render(idRef.current, chart);
        const sanitizedSvg = DOMPurify.sanitize(renderedSvg, {
          USE_PROFILES: { svg: true, svgFilters: true },
        });
        setSvg(sanitizedSvg);
      } catch (err) {
        console.error("Mermaid rendering error:", err);
        setError(err.message || "Failed to render diagram");
      } finally {
        setIsLoading(false);
      }
    };

    renderChart();
  }, [chart]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-4 bg-gray-50 rounded-lg border border-gray-200">
        <div className="flex items-center gap-2 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">Rendering diagram...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 rounded-lg border border-red-200">
        <div className="flex items-start gap-2">
          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-800">
              Failed to render Mermaid diagram
            </p>
            <p className="text-xs text-red-600 mt-1">{error}</p>
            <details className="mt-2">
              <summary className="text-xs text-red-600 cursor-pointer hover:underline">
                Show source
              </summary>
              <pre className="mt-2 p-2 bg-red-100 rounded text-xs overflow-x-auto">
                {chart}
              </pre>
            </details>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="mermaid-container my-4 p-4 bg-white rounded-lg border border-gray-200 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
});

MermaidChart.displayName = "MermaidChart";

export default MermaidChart;
