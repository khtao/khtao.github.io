#!/usr/bin/env bash
# 一次跑完所有回归测试。
#
#   bash tests/run-all.sh          # 全部
#   bash tests/run-all.sh --python # 只跑 Python
#
# Python 测试无第三方依赖；DOM 测试需要 jsdom（npm i jsdom），
# 没装时会自动跳过并提示，不会让整体失败。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

echo "──────── Python 测试（构建脚本 / 端到端）────────"
$PY -m unittest discover -s tests -v 2>&1 | tail -n 25
py_status=${PIPESTATUS[0]}

if [ "${1:-}" = "--python" ]; then
  exit $py_status
fi

echo
echo "──────── DOM 测试（浏览器行为回归）────────"
if node -e "require('jsdom')" >/dev/null 2>&1; then
  node tests/js/run-all.js
  js_status=$?
else
  echo "跳过：未安装 jsdom。"
  echo "  安装后重跑： npm i jsdom && node tests/js/run-all.js"
  js_status=0
fi

echo
if [ $py_status -eq 0 ] && [ $js_status -eq 0 ]; then
  echo "✅ 全部通过"
  exit 0
fi
echo "❌ 存在失败（Python=$py_status  DOM=$js_status）"
exit 1
