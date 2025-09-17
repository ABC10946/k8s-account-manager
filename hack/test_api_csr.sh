#!/bin/zsh
# REST APIでCSRを送信し、kubeconfigを取得するテストスクリプト

API_URL="http://localhost:5000/api/csr"
CSR_FILE="test.csr.b64"

if [ ! -f "$CSR_FILE" ]; then
  echo "CSRファイルが見つかりません: $CSR_FILE"
  exit 1
fi

CSR_B64=$(cat "$CSR_FILE")

RESPONSE=$(curl -s -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"csr": "'$CSR_B64'"}')

# 結果表示
echo "$RESPONSE"
