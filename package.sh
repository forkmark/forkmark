#!/bin/bash

# Exit on any error
set -e

echo "📦 Packaging Forkmark for distribution..."

# Define the output archive name
ARCHIVE_NAME="forkmark-release.zip"
ORIG_DIR=$(pwd)

# Clean up previous archives if they exist
rm -f "$ARCHIVE_NAME"

# Create a temporary directory to build the archive
TEMP_DIR=$(mktemp -d)
cp -r . "$TEMP_DIR/forkmark"

# Move into the temp directory to clean it up before zipping
cd "$TEMP_DIR/forkmark"

echo "🧹 Cleaning development and unnecessary files..."

# Remove git history
rm -rf .git
rm -f .gitignore

# Remove python virtual environments and cache
rm -rf .venv venv env
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# Remove frontend node_modules and build artifacts (if not intended for source distro)
# We will keep the source code so the customer can build it via docker-compose
rm -rf frontend/node_modules
rm -rf frontend/dist
rm -rf frontend/.next

# Remove IDE settings and OS specific files
rm -rf .idea .vscode
find . -type f -name ".DS_Store" -delete

# Remove SQLite database if it exists
rm -f backend/forkmark.db
rm -f test.db data/*.db

# Remove the packaging script itself from the archive
rm -f package.sh

# Remove dev-only Docker files (keep the simple stack for distribution)
rm -f docker-compose.yml  # production stack requires TLS certs + PG password

# Zip it up
echo "🗜️ Compressing to $ARCHIVE_NAME..."
cd "$TEMP_DIR"
zip -r "$ARCHIVE_NAME" forkmark/ > /dev/null

# Move it back to the original workspace
cd "$ORIG_DIR"
mv "$TEMP_DIR/$ARCHIVE_NAME" .

# Clean up temp directory
rm -rf "$TEMP_DIR"

echo "✅ Packaging complete: $ARCHIVE_NAME"
echo "You can now distribute this file securely."
