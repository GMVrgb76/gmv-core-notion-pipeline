#!/bin/sh
set -eu

exec "$HOME/.gmv_core/10_API/backup_service.py" create \
  --core "$HOME/.gmv_core" \
  --root "$HOME/.gmv_backups"
