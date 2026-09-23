#!/bin/bash

echo "Creating decoded setup script..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

TEMP_FILE=$(mktemp)

ENCODED_FILE="$SCRIPT_DIR/lab02_setup_encoded.txt"

if [[ "$OSTYPE" == "darwin"* ]]; then
    if base64 -D -i "$ENCODED_FILE" -o "$TEMP_FILE"; then
        mv "$TEMP_FILE" "$SCRIPT_DIR/lab02_setup_source.sh"
        rm "$ENCODED_FILE"
        echo "Decoded setup script created as lab02_setup_source.sh"
    else
        echo "Error: Failed to decode $ENCODED_FILE"
        rm -f "$TEMP_FILE"
        exit 1
    fi
else
    if base64 -d "$ENCODED_FILE" > "$TEMP_FILE"; then
        mv "$TEMP_FILE" "$SCRIPT_DIR/lab02_setup_source.sh"
        rm "$ENCODED_FILE"
        echo "Decoded setup script created as lab02_setup_source.sh"
    else
        echo "Error: Failed to decode $ENCODED_FILE"
        rm -f "$TEMP_FILE"
        exit 1
    fi
fi
