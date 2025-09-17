import base64
from flask import Flask, request, render_template_string

app = Flask(__name__)

# CSR入力フォーム
form_html = '''
    <form method="post">
        <label>Base64エンコードされたCSR:</label><br>
        <textarea name="csr" rows="10" cols="60"></textarea><br>
        <input type="submit" value="送信">
    </form>
'''

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

def generate_kubeconfig(cert, key, ca_cert, server, username):
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
                    "user": username
                }
            }
        ],
        "current-context": "default"
    }
    return yaml.dump(kubeconfig, allow_unicode=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        csr_b64 = request.form['csr']
        csr, error = decode_csr(csr_b64)
        if error:
            return error + form_html
        csr_name, err, api = create_k8s_csr(csr)
        if err:
            return err + form_html
        csr_status, err = wait_for_approval(api, csr_name)
        if err:
            return err + form_html
        cert = get_certificate(csr_status)
        # CA証明書取得
        from kubernetes import config
        kube_cfg = config.kube_config.KubeConfigMerger(config.kube_config.KUBE_CONFIG_DEFAULT_LOCATION)
        ca_cert = None
        server = None
        for cluster in kube_cfg.config['clusters']:
            ca_cert = base64.b64decode(cluster['cluster']['certificate-authority-data'])
            server = cluster['cluster']['server']
            break
        # CSRリソースには秘密鍵は含まれないため、CSR生成時の秘密鍵を利用する必要があります。
        # 今回はフォーム入力CSRのみ受け付けるため、秘密鍵はユーザー側で管理している前提です。
        # サンプルとして空文字列をセットします。
        key = b''
        username = csr_name
        kubeconfig_yaml = generate_kubeconfig(cert, key, ca_cert, server, username)
        return render_template_string('<h2>kubeconfig</h2><pre>{{ kubeconfig }}</pre>', kubeconfig=kubeconfig_yaml)
    return form_html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
