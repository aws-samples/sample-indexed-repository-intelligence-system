#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Script to add MIT-0 license headers to non-Python files

MARKDOWN_HEADER="<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->
"

YAML_HEADER="# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"

SHELL_HEADER="# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"

JS_HEADER="// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
"

HTML_HEADER="<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->
"

count=0
skipped=0

# Function to check if file already has copyright header
has_header() {
    local file=$1
    head -5 "$file" 2>/dev/null | grep -qi "Copyright Amazon.com"
}

# Function to add header to file
add_header() {
    local file=$1
    local header=$2
    local preserve_first_line=${3:-false}

    if has_header "$file"; then
        echo "  ✓ Already has header: $file"
        ((skipped++))
        return
    fi

    if [[ "$preserve_first_line" == "true" ]]; then
        # Preserve first line (e.g., shebang)
        first_line=$(head -1 "$file")
        rest=$(tail -n +2 "$file")
        {
            echo "$first_line"
            echo -n "$header"
            echo "$rest"
        } > "${file}.tmp"
    else
        # Just prepend header
        {
            echo -n "$header"
            cat "$file"
        } > "${file}.tmp"
    fi

    mv "${file}.tmp" "$file"
    echo "  + Added header: $file"
    ((count++))
}

echo "Processing Markdown files..."
find . -type f -name "*.md" \
    -not -path "./.venv/*" \
    -not -path "./venv/*" \
    -not -path "./node_modules/*" \
    -not -path "./.ash/*" \
    -not -path "./cdk.out/*" \
    -not -path "./.iris_cache/*" \
    | while read -r file; do
        add_header "$file" "$MARKDOWN_HEADER" false
    done

echo ""
echo "Processing YAML files..."
find . -type f \( -name "*.yaml" -o -name "*.yml" \) \
    -not -path "./.venv/*" \
    -not -path "./venv/*" \
    -not -path "./node_modules/*" \
    -not -path "./.ash/*" \
    -not -path "./cdk.out/*" \
    | while read -r file; do
        add_header "$file" "$YAML_HEADER" false
    done

echo ""
echo "Processing Shell scripts..."
find . -type f -name "*.sh" \
    -not -path "./.venv/*" \
    -not -path "./venv/*" \
    | while read -r file; do
        # Check if has shebang
        if head -1 "$file" | grep -q "^#!"; then
            add_header "$file" "$SHELL_HEADER" true
        else
            add_header "$file" "$SHELL_HEADER" false
        fi
    done

echo ""
echo "Processing JavaScript files..."
find . -type f -name "*.js" \
    -not -path "./.venv/*" \
    -not -path "./node_modules/*" \
    -not -path "./build/*" \
    -not -path "./dist/*" \
    | while read -r file; do
        add_header "$file" "$JS_HEADER" false
    done

echo ""
echo "Processing HTML files..."
find . -type f -name "*.html" \
    -not -path "./.venv/*" \
    -not -path "./node_modules/*" \
    -not -path "./build/*" \
    | while read -r file; do
        add_header "$file" "$HTML_HEADER" false
    done

echo ""
echo "Processing Dockerfiles..."
find . -type f \( -name "Dockerfile*" -o -name "*.dockerfile" \) \
    -not -path "./.venv/*" \
    -not -path "./node_modules/*" \
    | while read -r file; do
        add_header "$file" "$SHELL_HEADER" false
    done

echo ""
echo "Processing other config files..."
# Git hooks
if [[ -d ".githooks" ]]; then
    find .githooks -type f | while read -r file; do
        add_header "$file" "$SHELL_HEADER" true
    done
fi

# requirements.txt files
find . -type f -name "requirements*.txt" \
    -not -path "./.venv/*" \
    -not -path "./venv/*" \
    | while read -r file; do
        add_header "$file" "$SHELL_HEADER" false
    done

echo ""
echo "===================================="
echo "✓ Added headers to $count files"
echo "✓ Skipped $skipped files (already had headers)"
echo "===================================="
