#!/bin/bash
# Script to check latest versions of packages in backend/requirements.txt

echo "Checking latest versions from PyPI..."

while IFS= read -r line; do
    # Skip comments, empty lines, and special lines
    if [[ $line =~ ^# ]] || [[ -z "$line" ]] || [[ $line =~ ^-- ]]; then
        continue
    fi
    # Extract package name before == or ~=
    package=$(echo "$line" | sed 's/[~=<>].*//' | sed 's/\[.*\]//')
    if [[ -n "$package" ]]; then
        echo "Checking $package..."
        version=$(pip index versions "$package" 2>/dev/null | grep -i "LATEST:" | awk '{print $2}')
        if [[ -n "$version" ]]; then
            echo "$package: $version"
        else
            echo "$package: Not found or error"
        fi
    fi
done < backend/requirements.txt