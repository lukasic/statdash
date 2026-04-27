#!/bin/sh
set -e

RESOLVER=$(awk 'NR==1{print $2}' /etc/resolv.conf)
export RESOLVER

envsubst '${BACKEND_URL} ${RESOLVER}' \
  < /etc/nginx/nginx.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
