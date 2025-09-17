from cryptography import x509
from cryptography.hazmat.backends import default_backend
import base64
from flask import Flask, request, render_template_string
from flask import Flask, request, jsonify

app = Flask(__name__)


def decode_csr(csr_b64):
    try:
        return base64.b64decode(csr_b64.encode()), None
    except Exception as e:
        return None, f"CSRのデコードに失敗しました: {e}"

def extract_cn_from_csr(csr_bytes):
    try:
        csr = x509.load_der_x509_csr(csr_bytes, default_backend())
    except Exception:
        csr = x509.load_pem_x509_csr(csr_bytes, default_backend())
    subject = csr.subject
    cn = None
    for attr in subject:
        if attr.oid == x509.NameOID.COMMON_NAME:
            cn = attr.value
            break
    return cn
    try:
        return base64.b64decode(csr_b64.encode()), None
    except Exception as e:
        return None, f"CSRのデコードに失敗しました: {e}"
    
def create_k8s_csr(csr):
    import uuid
    from kubernetes import client, config
    config.load_kube_config()
    api = client.CertificatesV1Api()
    csr_name = f"user-csr-{uuid.uuid4().hex[:8]}"
    csr_obj = client.V1CertificateSigningRequest(
        metadata=client.V1ObjectMeta(name=csr_name),
        spec=client.V1CertificateSigningRequestSpec(
            request=base64.b64encode(csr).decode(),
            signer_name="kubernetes.io/kube-apiserver-client",
            usages=["client auth"],
            groups=["system:authenticated"]
        )
    )
    try:
        api.create_certificate_signing_request(body=csr_obj)
    except Exception as e:
        return None, f"Kubernetes CSR作成に失敗しました: {e}", None
    return csr_name, None, api


def get_certificate(csr_status):
    return base64.b64decode(csr_status.status.certificate)

def generate_kubeconfig(cert, key, ca_cert, server, username, namespace):
    import yaml
    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": "kubernetes",
                "cluster": {
                    "certificate-authority-data": base64.b64encode(ca_cert).decode(),
                    "server": server
                }
            }
        ],
        "users": [
            {
                "name": username,
                "user": {
                    "client-certificate-data": base64.b64encode(cert).decode(),
                    "client-key-data": base64.b64encode(key).decode()
                }
            }
        ],
        "contexts": [
            {
                "name": "default",
                "context": {
                    "cluster": "kubernetes",
                    "user": username,
                    "namespace": namespace
                }
            }
        ],
        "current-context": "default"
    }
    return yaml.dump(kubeconfig, allow_unicode=True)

# REST APIエンドポイント（2段階方式）
@app.route('/api/csr', methods=['POST'])
def api_csr():
    data = request.get_json()
    csr_b64 = data.get('csr')
    if not csr_b64:
        return jsonify({"error": "csrフィールドが必要です"}), 400
    csr, error = decode_csr(csr_b64)
    if error:
        return jsonify({"error": error}), 400
    csr_name, err, api = create_k8s_csr(csr)
    if err:
        return jsonify({"error": err}), 500
    # CSRのCN(subject)からユーザ名を取得
    username = extract_cn_from_csr(csr)
    # CSR名とユーザ名を返す
    return jsonify({"csr_name": csr_name, "username": username})

# CSRステータス取得API
@app.route('/api/csr/<csr_name>', methods=['GET'])
def api_csr_status(csr_name):
    from kubernetes import client, config
    config.load_kube_config()
    api = client.CertificatesV1Api()
    try:
        csr_status = api.read_certificate_signing_request(name=csr_name)
    except Exception as e:
        return jsonify({"error": f"CSR取得に失敗しました: {e}"}), 404
    if not csr_status.status or not csr_status.status.certificate:
        return jsonify({"status": "pending"})
    cert = get_certificate(csr_status)
    # CA証明書取得
    kube_cfg = config.kube_config.KubeConfigMerger(config.kube_config.KUBE_CONFIG_DEFAULT_LOCATION)
    ca_cert = None
    server = None
    for cluster in kube_cfg.config['clusters']:
        ca_cert = base64.b64decode(cluster['cluster']['certificate-authority-data'])
        server = cluster['cluster']['server']
        break
    key = b''
    # CSRリソースからCSR本体を取得し、CN(subject)からユーザ名を抽出
    csr_bytes = base64.b64decode(csr_status.spec.request)
    username = extract_cn_from_csr(csr_bytes)
    namespace = username

    # --- ここからnamespace, role, rolebinding自動作成 ---
    api_core = client.CoreV1Api()
    api_rbac = client.RbacAuthorizationV1Api()
    # Namespace作成
    try:
        api_core.create_namespace(client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace)))
    except client.exceptions.ApiException as e:
        if e.status != 409:
            return jsonify({"error": f"Namespace作成失敗: {e}"}), 500
    # Role作成
    role_body = client.V1Role(
        metadata=client.V1ObjectMeta(name=namespace, namespace=namespace),
        rules=[client.V1PolicyRule(
            api_groups=["*"],
            resources=["*"],
            verbs=["get", "list", "watch", "create", "update", "patch", "delete"]
        )]
    )
    try:
        api_rbac.create_namespaced_role(namespace=namespace, body=role_body)
    except client.exceptions.ApiException as e:
        if e.status != 409:
            return jsonify({"error": f"Role作成失敗: {e}"}), 500
    # RoleBinding作成
    rolebinding_body = client.V1RoleBinding(
        metadata=client.V1ObjectMeta(name=namespace, namespace=namespace),
        role_ref=client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="Role",
            name=namespace
        ),
        subjects=[{
            "kind": "User",
            "name": username,
            "apiGroup": "rbac.authorization.k8s.io"
        }]
    )
    try:
        api_rbac.create_namespaced_role_binding(namespace=namespace, body=rolebinding_body)
    except client.exceptions.ApiException as e:
        if e.status != 409:
            return jsonify({"error": f"RoleBinding作成失敗: {e}"}), 500
    # --- ここまで自動作成 ---

    kubeconfig_yaml = generate_kubeconfig(cert, key, ca_cert, server, username, namespace)
    return jsonify({"status": "approved", "kubeconfig": kubeconfig_yaml})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
