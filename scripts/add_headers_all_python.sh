#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Script to add MIT-0 license headers to ALL Python files

PYTHON_HEADER="# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"

count=0
skipped=0

# Function to check if file already has copyright header
has_header() {
    local file=$1
    head -5 "$file" 2>/dev/null | grep -q "Copyright Amazon.com"
}

# Function to add header to Python file
add_python_header() {
    local file=$1

    if has_header "$file"; then
        echo "  ✓ Already has header: $file"
        ((skipped++))
        return
    fi

    # Check if file starts with shebang
    if head -1 "$file" | grep -q "^#!"; then
        # Preserve shebang
        shebang=$(head -1 "$file")
        rest=$(tail -n +2 "$file")
        {
            echo "$shebang"
            echo -n "$PYTHON_HEADER"
            echo "$rest"
        } > "${file}.tmp"
        mv "${file}.tmp" "$file"
        echo "  + Added header (preserved shebang): $file"
    else
        # No shebang, just prepend header
        {
            echo -n "$PYTHON_HEADER"
            cat "$file"
        } > "${file}.tmp"
        mv "${file}.tmp" "$file"
        echo "  + Added header: $file"
    fi
    ((count++))
}

# Find all .py files, excluding virtual environments and cache directories
find . -type f -name "*.py" \
    -not -path "./.venv/*" \
    -not -path "./venv/*" \
    -not -path "./.mypy_cache/*" \
    -not -path "./.pytest_cache/*" \
    -not -path "./node_modules/*" \
    -not -path "./.ash/*" \
    -not -path "./cdk.out/*" \
    -not -path "./.iris_cache/*" \
    | while read -r file; do
        add_python_header "$file"
    done

echo ""
echo "===================================="
echo "✓ Added headers to $count files"
echo "✓ Skipped $skipped files (already had headers)"
echo "===================================="
