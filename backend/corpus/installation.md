source: https://olake.io/docs/getting-started/quickstart/
# OLake UI Quickstart

The official OLake UI quickstart recommends Docker Compose. The UI manages
OLake Go jobs, sources, destinations, and configurations. The quickstart starts
the UI, OLake backend, and required dependencies together.

Prerequisites:
- Docker installed (Docker Desktop is recommended).
- Docker Compose (included with Docker Desktop).
- At least 4 GB RAM available for Docker.
- Port 8000 available.

Start the stack:
```sh
curl -sSL https://raw.githubusercontent.com/datazip-inc/olake-ui/master/docker-compose.yml | docker compose -f - up -d
```

Open the UI at http://localhost:8000. The quickstart lists the initial login as
username `admin` and password `password`. Change default credentials before
exposing any deployment beyond a local development environment.

For installation details and updates, see the official
[OLake UI Quickstart](https://olake.io/docs/getting-started/quickstart/).
