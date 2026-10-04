#!/usr/bin/env bash
# SSI - TP IoT/IIoT - Grupo 18
# Genera una CA de laboratorio y el certificado del broker para TLS.
# Solo para el laboratorio de la demo (no es una PKI de produccion).
#
# Uso:
#   ./gen-certs.sh 192.168.1.100       # IP o hostname del broker
#
set -euo pipefail

CN="${1:-192.168.1.100}"
OUT="../broker/certs"
mkdir -p "$OUT"
cd "$OUT"

echo "[*] Generando CA de laboratorio..."
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 365 -key ca.key -out ca.crt \
  -subj "/C=AR/O=SSI-Lab/CN=SSI-Lab-CA"

echo "[*] Generando certificado del broker para CN=$CN ..."
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
  -subj "/C=AR/O=SSI-Lab/CN=$CN"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -days 365

rm -f server.csr
echo "[+] Listo. Archivos en $OUT :"
ls -1
echo
echo "    - ca.crt      -> copiar al ESP32 y al SCADA (para validar al broker)"
echo "    - server.crt  -> lo usa el broker"
echo "    - server.key  -> lo usa el broker (mantener privado)"
