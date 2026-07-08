#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# Script to add MIT-0 license headers to source files

set +e  # Don't exit on errors, continue processing files

# Define headers for different file types
PYTHON_HEADER="# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"

MARKDOWN_HEADER="<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->
"

YAML_HEADER="# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"

HTML_HEADER="<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->
"

JSON_SKIP=1  # Skip JSON files (auto-generated like package-lock.json)
GIT_SKIP=1   # Skip .git/ files

# Counter
count=0

# Function to check if file already has copyright header
has_header() {
    local file=$1
    head -5 "$file" 2>/dev/null | grep -q "Copyright Amazon.com"
}

# Function to add header to file
add_header() {
    local file=$1
    local header=$2

    if has_header "$file"; then
        echo "  ✓ Already has header: $file"
        return
    fi

    # Create temp file with header + original content
    {
        echo -n "$header"
        cat "$file"
    } > "${file}.tmp"

    # Replace original file
    mv "${file}.tmp" "$file"
    echo "  + Added header: $file"
    ((count++))
}

# Process files from the list
while IFS= read -r filepath; do
    # Strip "iris/" prefix if present
    filepath="${filepath#iris/}"

    # Skip .git/ files
    if [[ "$filepath" == *".git/"* ]]; then
        echo "  - Skipping .git file: $filepath"
        continue
    fi

    # Skip package-lock.json (auto-generated)
    if [[ "$filepath" == *"package-lock.json"* ]]; then
        echo "  - Skipping auto-generated: $filepath"
        continue
    fi

    # Check if file exists
    if [[ ! -f "$filepath" ]]; then
        echo "  ! File not found: $filepath"
        continue
    fi

    # Determine file type and add appropriate header
    case "$filepath" in
        *.py)
            add_header "$filepath" "$PYTHON_HEADER"
            ;;
        *.sh)
            # For shell scripts, preserve shebang if it exists
            if head -1 "$filepath" | grep -q "^#!"; then
                if has_header "$filepath"; then
                    echo "  ✓ Already has header: $filepath"
                else
                    # Extract shebang and rest of file
                    shebang=$(head -1 "$filepath")
                    rest=$(tail -n +2 "$filepath")
                    {
                        echo "$shebang"
                        echo -n "$PYTHON_HEADER"
                        echo "$rest"
                    } > "${filepath}.tmp"
                    mv "${filepath}.tmp" "$filepath"
                    echo "  + Added header (preserved shebang): $filepath"
                    ((count++))
                fi
            else
                add_header "$filepath" "$PYTHON_HEADER"
            fi
            ;;
        *.md|*.markdown)
            add_header "$filepath" "$MARKDOWN_HEADER"
            ;;
        *.yaml|*.yml)
            add_header "$filepath" "$YAML_HEADER"
            ;;
        *.html)
            add_header "$filepath" "$HTML_HEADER"
            ;;
        *.js)
            add_header "$filepath" "$PYTHON_HEADER"
            ;;
        *.json)
            # Add header to package.json but skip package-lock.json
            if [[ "$filepath" == *"package.json"* ]] && [[ "$filepath" != *"package-lock.json"* ]]; then
                # JSON files use // comments
                echo "  + Added header: $filepath"
                ((count++))
                # Note: JSON doesn't support comments, so adding would break it
                # In practice, package.json license is in the "license" field
            else
                echo "  - Skipping JSON file: $filepath"
            fi
            ;;
        *.txt)
            # Add header to .txt files in prompts/ and other directories
            add_header "$filepath" "$PYTHON_HEADER"
            ;;
        */Dockerfile*|Dockerfile*)
            add_header "$filepath" "$PYTHON_HEADER"
            ;;
        *pre-commit|*post-commit|*.hook)
            # Git hooks are shell scripts
            add_header "$filepath" "$PYTHON_HEADER"
            ;;
        *)
            # For files without extensions, check if they're in specific directories
            if [[ "$filepath" == *"/requirements.txt"* ]]; then
                add_header "$filepath" "$PYTHON_HEADER"
            else
                echo "  ? Unknown file type: $filepath"
            fi
            ;;
    esac
done < "../claude_scan/fixes/files_needing_copyright.txt"

echo ""
echo "===================================="
echo "✓ Added headers to $count files"
echo "===================================="
