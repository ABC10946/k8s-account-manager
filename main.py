import base64
from flask import Flask, request, render_template_string
from flask import Flask, request, jsonify

app = Flask(__name__)


def decode_csr(csr_b64):
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

def wait_for_approval(api, csr_name, timeout=60):
    import time
    for _ in range(timeout):
        csr_status = api.read_certificate_signing_request(name=csr_name)
        if csr_status.status and csr_status.status.certificate:
            return csr_status, None
        time.sleep(2)
    return None, "管理者による承認がタイムアウトしました。"


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
    # CSR名のみ返す（証明書はまだ返さない）
    return jsonify({"csr_name": csr_name})

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
    username = csr_name
    namespace = csr_name
    kubeconfig_yaml = generate_kubeconfig(cert, key, ca_cert, server, username, namespace)
    return jsonify({"status": "approved", "kubeconfig": kubeconfig_yaml})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
