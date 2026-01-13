# Proxy Dashboard

Automatic dashboard generated from Nginx Proxy Manager data.

## Setup

To set up the frontend to connect to the backend,

```sh
nano frontend/.env.local
```

and place the following content inside:

```sh
NEXT_PUBLIC_API_BASE=http://192.168.178.50:8080"
```

then run `./setup.sh` to install dependencies and setup services.

## Other Settings

```sh
export NPM_BASE_URL="http://192.168.178.68:81"
export ADMIN_USER="a"
export ADMIN_PASS="a"

# Optional
export DASH_CORS_ORIGINS="http://localhost:5173,http://localhost:3000,https://localhost:3000,https://localhost:5173"
```

## Restart

```sh
systemctl restart myapp-frontend.service
systemctl restart myapp-backend.service
```
