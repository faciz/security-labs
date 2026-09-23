#!/bin/bash

echo "Creating encoded setup script..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SOURCE_FILE="$SCRIPT_DIR/lab02_setup_source.sh"

ENCODED_FILE="$SCRIPT_DIR/lab02_setup_encoded.txt"

TEMP_FILE=$(mktemp)

if [[ "$OSTYPE" == "darwin"* ]]; then
    if base64 -i "$SOURCE_FILE" -o "$TEMP_FILE"; then
        mv "$TEMP_FILE" "$ENCODED_FILE"
        rm "$SOURCE_FILE"
        echo "Created lab02_setup_encoded.txt - users can run this without seeing the source!"
    else
        echo "Error: Failed to encode $SOURCE_FILE"
        rm -f "$TEMP_FILE"
        exit 1
    fi
else
    if base64 "$SOURCE_FILE" > "$TEMP_FILE"; then
        mv "$TEMP_FILE" "$ENCODED_FILE"
        rm "$SOURCE_FILE"
        echo "Created lab02_setup_encoded.txt - users can run this without seeing the source!"
    else
        echo "Error: Failed to encode $SOURCE_FILE"
        rm -f "$TEMP_FILE"
        exit 1
    fi
fi
