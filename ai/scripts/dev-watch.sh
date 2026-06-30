#!/bin/bash
# Frontend dev watch script
# Watches frontend-src/ for changes, auto-builds, and syncs to frontend/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_SRC="$PROJECT_DIR/frontend-src"
FRONTEND_DIST="$FRONTEND_SRC/dist/web"
FRONTEND_DEST="$PROJECT_DIR/frontend"

echo "[dev-watch] Starting Vite build watch..."
cd "$FRONTEND_SRC"

# First do a clean build
echo "[dev-watch] Initial build..."
npx vite build --config vite.config.ts --mode web

# Sync to frontend/
echo "[dev-watch] Syncing to frontend/..."
cp "$FRONTEND_DIST/assets/"*.js "$FRONTEND_DEST/assets/"
cp "$FRONTEND_DIST/assets/"*.css "$FRONTEND_DEST/assets/"

# Update index.html to keep localStorage cleanup script
node -e "
const fs = require('fs');
const html = fs.readFileSync('$FRONTEND_DIST/index.html', 'utf-8');
const jsFile = fs.readdirSync('$FRONTEND_DIST/assets').find(f => f.endsWith('.js'));
const cssFile = fs.readdirSync('$FRONTEND_DIST/assets').find(f => f.endsWith('.css'));

const cleanup = \`    <script>
      (function() {
        var keys = ['wsUrl', 'baseUrl', 'backgroundUrl', 'modelInfo'];
        for (var i = 0; i < keys.length; i++) {
          var val = localStorage.getItem(keys[i]);
          if (val && val.indexOf('12393') !== -1) {
            localStorage.removeItem(keys[i]);
            console.log('[Bridge] Cleared stale localStorage: ' + keys[i]);
          }
        }
      })();
    </script>\`;

const newHtml = html.replace('</head>', cleanup + '\n  </head>');
fs.writeFileSync('$FRONTEND_DEST/index.html', newHtml);
console.log('[dev-watch] index.html updated with cleanup script');
"

echo "[dev-watch] Initial sync complete!"
echo "[dev-watch] Watching for changes..."

# Watch mode
npx vite build --config vite.config.ts --mode web --watch
