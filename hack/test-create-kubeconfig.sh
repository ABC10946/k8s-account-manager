#!/bin/zsh
# CSR名と秘密鍵ファイルを使ってkubeconfigを取得・編集するスクリプト
# 必要: jq, curl, base64, CSR名, 秘密鍵ファイル

API_URL="http://localhost:5000/api/csr"
CSR_NAME="$1"        # 第一引数: CSR名
KEY_FILE="$2"        # 第二引数: 秘密鍵ファイル

if [ -z "$CSR_NAME" ]; then
  echo "Usage: $0 <csr_name> <key_file>"
  exit 1
fi
if [ ! -f "$KEY_FILE" ]; then
  echo "秘密鍵ファイルが見つかりません: $KEY_FILE"
  exit 1
fi

# 1. ステータス取得（kubeconfig取得）
STATUS_URL="${API_URL}/$CSR_NAME"
RESPONSE=$(curl -s "$STATUS_URL")

if ! echo "$RESPONSE" | grep -q 'kubeconfig'; then
  echo "kubeconfig未取得: $RESPONSE"
  exit 1
fi

KUBECONFIG_YAML=$(echo "$RESPONSE" | jq -r .kubeconfig)

# 2. 秘密鍵をbase64エンコード
KEY_B64=$(base64 -w 0 "$KEY_FILE")

# 3. kubeconfigのclient-key-dataを書き換え
#    (yamlをjqで編集できないため、sedで置換)
KUBECONFIG_YAML_EDITED=$(echo "$KUBECONFIG_YAML" | \
  sed "s|client-key-data: .*|client-key-data: $KEY_B64|")

# 4. 結果表示
echo "$KUBECONFIG_YAML_EDITED"
