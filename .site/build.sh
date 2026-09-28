#!/usr/bin/env bash
# 把這個筆記資料夾建成 Quartz 網站，輸出到 ./public
# Cloudflare Pages 的 Build command：bash .site/build.sh
# 本機預覽：bash .site/build.sh --serve
set -euo pipefail

QUARTZ_REPO="https://github.com/jackyzha0/quartz.git"
QUARTZ_REF="97a2d05f80c4c50534959b1d0d41cc4b3895625e"   # 固定版本，要升級再改這行

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${QUARTZ_WORKDIR:-$ROOT/.site/.build}"
Q="$WORK/quartz"

# 1. 取得 Quartz（只在第一次或版本變更時下載）
if [ ! -d "$Q/.git" ] || [ "$(git -C "$Q" rev-parse HEAD)" != "$QUARTZ_REF" ]; then
  rm -rf "$Q"
  mkdir -p "$WORK"
  git clone --quiet "$QUARTZ_REPO" "$Q"
  git -C "$Q" checkout --quiet "$QUARTZ_REF"
fi
[ -d "$Q/node_modules" ] || (cd "$Q" && npm ci --no-audit --no-fund)

# 2. 放入設定與筆記
cp "$ROOT/.site/quartz.config.yaml" "$Q/quartz.config.yaml"
rm -rf "$Q/content"
mkdir -p "$Q/content"
rsync -a \
  --exclude '.git' --exclude '.site' --exclude '.obsidian' --exclude '.DS_Store' \
  --exclude 'Tintinalli text book' --exclude '00_急診專案' --exclude 'public' \
  "$ROOT/" "$Q/content/"
# README 當首頁
mv "$Q/content/README.md" "$Q/content/index.md"
# 首頁拿掉沒有發佈的 00_急診專案 段落
python3 - "$Q/content/index.md" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = re.sub(r"^## 00 急診專案\n.*?(?=^## )", "", t, flags=re.S | re.M)
open(p, "w", encoding="utf-8").write(t)
PY

# 3. 建置
cd "$Q"
npx quartz plugin install --from-config
if [ "${1:-}" = "--serve" ]; then
  npx quartz build --serve
else
  npx quartz build
  rm -rf "$ROOT/public"
  cp -R "$Q/public" "$ROOT/public"
  echo "✅ 網站已輸出到 $ROOT/public"
fi
