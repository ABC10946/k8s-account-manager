openssl genrsa -out test.key 2048
openssl req -new -key test.key -out test.csr -subj "/CN=Test/O=Test"
cat test.csr|base64 -w 0 > test.csr.b64
cat test.key|base64 -w 0 > test.key.b64