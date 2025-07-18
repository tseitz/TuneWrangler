#!/bin/bash

# TuneWrangler CLI Installation Script

set -e

echo "🎵 Installing TuneWrangler CLI..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create the CLI executable
CLI_SCRIPT="$SCRIPT_DIR/tunewrangler"

cat > "$CLI_SCRIPT" << 'EOF'
#!/bin/bash

# TuneWrangler CLI Wrapper
# This script allows you to run TuneWrangler from anywhere

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the CLI with all arguments passed through
deno run --allow-read --allow-write --allow-run --allow-net --allow-env --allow-sys "$SCRIPT_DIR/src/cli/main.ts" "$@"
EOF

# Make the script executable
chmod +x "$CLI_SCRIPT"

echo "✅ TuneWrangler CLI installed successfully!"
echo ""
echo "You can now run TuneWrangler using:"
echo "  ./tunewrangler --help"
echo ""
echo "To make it available system-wide, add this to your PATH:"
echo "  export PATH=\"$SCRIPT_DIR:\$PATH\""
echo ""
echo "Or create a symlink:"
echo "  sudo ln -s \"$CLI_SCRIPT\" /usr/local/bin/tunewrangler"
echo ""
echo "Then you can run:"
echo "  tunewrangler --help" 