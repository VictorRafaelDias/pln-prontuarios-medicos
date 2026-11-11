#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "Primeira execução: instalando dependências..."
  python3 setup.py
fi
[ -d node_modules ] || { npm install --no-audit --no-fund; npm --prefix frontend install --no-audit --no-fund; }
echo "Abra http://localhost:5173  (API na porta 8010)"
npm run dev
