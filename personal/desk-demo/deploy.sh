#!/bin/sh
# Builds the desk with example data, adds the company page and the rates, and deploys to Cloudflare.
set -e
cd "$(dirname "$0")/../../frontend" && VITE_DEMO=1 npm run build
cp -R ../personal/desk-demo/site/. dist/
cd ../personal/desk-demo && NODE_OPTIONS=--no-network-family-autoselection npx wrangler deploy
