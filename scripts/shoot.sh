#!/bin/zsh
# Usage: shoot.sh <name> <url> [height]
# Full-height headless Chrome screenshot -> shots/<name>.jpg (1440 wide)
set -u
name="$1"; url="$2"; h="${3:-5200}"
root="$HOME/Code/start-hack-competitors"
tmp=$(mktemp -d)
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --hide-scrollbars --no-first-run --mute-audio \
  --user-data-dir="$tmp/profile" \
  --user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36" \
  --window-size=1440,$h --virtual-time-budget=12000 --timeout=45000 \
  --screenshot="$tmp/shot.png" "$url" >/dev/null 2>&1 &
pid=$!
( sleep 70; kill -9 $pid 2>/dev/null ) &
killer=$!
wait $pid 2>/dev/null
kill $killer 2>/dev/null
if [ -s "$tmp/shot.png" ]; then
  sips -s format jpeg -s formatOptions 72 "$tmp/shot.png" --out "$root/shots/$name.jpg" >/dev/null 2>&1
  echo "ok   $name"
else
  echo "FAIL $name $url"
fi
rm -rf "$tmp"
