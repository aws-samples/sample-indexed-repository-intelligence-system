// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { memo, useMemo } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { prism } from "react-syntax-highlighter/dist/esm/styles/prism";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import MermaidChart from "./MermaidChart";

// Supported languages mapping
const languageMap = {
  // JavaScript family
  javascript: "javascript",
  js: "javascript",
  jsx: "jsx",
  typescript: "typescript",
  ts: "typescript",
  tsx: "tsx",

  // Python
  python: "python",
  py: "python",

  // Web technologies
  json: "json",
  css: "css",
  scss: "scss",
  sass: "sass",
  html: "markup",
  xml: "markup",
  svg: "markup",

  // Documentation
  markdown: "markdown",
  md: "markdown",

  // Configuration
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  ini: "ini",

  // Database
  sql: "sql",
  mysql: "sql",
  postgresql: "sql",
  sqlite: "sql",

  // Shell/Scripts
  bash: "bash",
  shell: "bash",
  sh: "bash",
  zsh: "bash",
  fish: "bash",
  powershell: "powershell",
  ps1: "powershell",

  // Systems programming
  c: "c",
  cpp: "cpp",
  "c++": "cpp",
  cxx: "cpp",
  java: "java",
  go: "go",
  rust: "rust",
  rs: "rust",

  // Other popular languages
  php: "php",
  ruby: "ruby",
  rb: "ruby",
  swift: "swift",
  kotlin: "kotlin",
  scala: "scala",
  r: "r",
  matlab: "matlab",

  // Functional languages
  haskell: "haskell",
  hs: "haskell",
  clojure: "clojure",
  clj: "clojure",
  elixir: "elixir",
  ex: "elixir",

  // Other formats
  dockerfile: "dockerfile",
  docker: "dockerfile",
  makefile: "makefile",
  make: "makefile",
  diff: "diff",
  patch: "diff",
  git: "git",
  gitignore: "gitignore",

  // Fallbacks
  text: "text",
  txt: "text",
  plain: "text",
};

const CodeBlock = memo(
  ({
    children,
    className,
    theme = "light",
    showLanguageLabel = false,
    ...props
  }) => {
    // Memoize language detection and processing
    const { language, mappedLanguage, processedChildren } = useMemo(() => {
      const match = /language-(\w+)/.exec(className || "");
      const lang = match ? match[1].toLowerCase() : "";
      const mapped = languageMap[lang] || "text";
      const processed = String(children).replace(/\n$/, "");

      return {
        language: lang,
        mappedLanguage: mapped,
        processedChildren: processed,
      };
    }, [className, children]);

    // Memoize theme selection
    const selectedTheme = useMemo(() => {
      return theme === "dark" ? vscDarkPlus : oneLight;
    }, [theme]);

    const codeTagProps = useMemo(
      () => ({
        style: {
          fontFamily: "'Monaco', 'Menlo', 'Ubuntu Mono', monospace",
        },
      }),
      [],
    );

    // Handle inline code (no className usually means inline)
    if (!className) {
      return (
        <code className="inline-code" {...props}>
          {children}
        </code>
      );
    }

    // Handle Mermaid diagrams
    if (language === "mermaid") {
      return <MermaidChart chart={processedChildren} />;
    }

    return (
      <div className="code-block-container">
        {showLanguageLabel && language && (
          <div className="code-language-label">{language}</div>
        )}
        <SyntaxHighlighter
          language={mappedLanguage}
          style={selectedTheme}
          codeTagProps={codeTagProps}
          {...props}
        >
          {processedChildren}
        </SyntaxHighlighter>
      </div>
    );
  },
);

CodeBlock.displayName = "CodeBlock";

export default CodeBlock;
