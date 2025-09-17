# k8s-account-manager

Kubernetesクラスタ用のユーザー管理・kubeconfig発行APIサービスです。

## 概要
- ユーザーがCSR（証明書署名要求）をAPI経由で登録
- 管理者がCSRを承認
- 承認後、APIでkubeconfigを取得可能
- kubeconfigのユーザー名・namespaceはCSRのCN(subject)に準拠
- namespace/Role/RoleBindingは自動作成

## 主要API

### 1. CSR登録
```
POST /api/csr
Content-Type: application/json
{
  "csr": "<base64エンコードされたCSR>"
}
```
- レスポンス: `{ "csr_name": "...", "username": "..." }`

### 2. CSRステータス・kubeconfig取得
```
GET /api/csr/<csr_name>
```
- 未承認: `{ "status": "pending" }`
- 承認済み: `{ "status": "approved", "kubeconfig": "..." }`

## 自動リソース作成
- CSRのCN(subject)をユーザー名・namespace名として利用
- namespace, Role, RoleBindingを自動作成
  - Role/RoleBindingの権限は全リソース・全操作（例: get/list/create/delete...）

## hackスクリプト
- `test/` ディレクトリにAPI操作・運用補助用のシェルスクリプトを配置
  - CSR登録、kubeconfig取得、手動承認補助など

## テスト
- 単体テスト: `tests/test_main_unit.py`
  - `python -m unittest tests.test_main_unit`

## 必要な環境
- Python 3.10+
- Flask
- kubernetes
- cryptography
- kubeconfig（クラスタ外からAPI操作する場合）

## 注意事項
- CSR承認は管理者が手動で行う必要あり
- 自動作成されるnamespace/Role/RoleBindingはユーザーごと
- セキュリティ要件に応じてRole権限を調整してください

## ライセンス
MIT License
