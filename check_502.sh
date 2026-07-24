#!/bin/bash
# CHECK
echo "== containers =="
docker ps --format '{{.Names}}: {{.Status}}'
echo "== recent 502s =="
docker logs ckdo_nginx --since 30m 2>&1 | grep -c " 502 "
echo "== root cause (buffer too small) =="
docker logs ckdo_nginx --since 30m 2>&1 | grep -c "upstream sent too big header"

# ACTION — add proxy buffers to nginx config once, then reload (no restart needed)
CONF=/home/dashboarduser/ckdo/ckdo-dashboard/nginx/nginx.dev.conf
if ! grep -q proxy_buffer_size "$CONF"; then
  sed -i '/client_max_body_size 50M;/a\  proxy_buffer_size 128k;\n  proxy_buffers 4 256k;\n  proxy_busy_buffers_size 256k;' "$CONF"
  docker exec ckdo_nginx nginx -s reload
  echo "patched + reloaded"
else
  echo "already patched"
fi
