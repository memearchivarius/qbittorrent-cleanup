# qBittorrent Cleanup

Автоматическое удаление старых торрентов с одинаковым путем сохранения.

## Использование

```yaml
version: '3.8'
services:
  cleanup:
    image: ghcr.io/memearchivarius/qbittorrent-cleanup:latest
    environment:
      - QB_URL=http://qbittorrent:8080
      - QB_USER=admin
      - QB_PASS=adminadmin
      - DRY_RUN=true
      - DELETE_FILES=false
    restart: unless-stopped
```
