#!/bin/bash

echo "Setting up Offensive Security Lab 01..."

SCRIPT_DIR="$(dirname "$0")"
SOURCE_SCRIPT="$SCRIPT_DIR/.util/lab01_setup_source.sh"
ENCODED_SCRIPT="$SCRIPT_DIR/.util/lab01_setup_encoded.txt"

# Check if the decoded source script exists
if [ -f "$SOURCE_SCRIPT" ]; then
    chmod +x "$SOURCE_SCRIPT"
    "$SOURCE_SCRIPT"
elif [ -f "$ENCODED_SCRIPT" ]; then
    TEMP_SCRIPT=$(mktemp)
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        base64 -D -i "$ENCODED_SCRIPT" -o "$TEMP_SCRIPT"
    else
        base64 -d "$ENCODED_SCRIPT" > "$TEMP_SCRIPT"
    fi

    chmod +x "$TEMP_SCRIPT"
    "$TEMP_SCRIPT"
    rm -f "$TEMP_SCRIPT"
else
    echo "Error: No setup file found!"
    exit 1
fi

