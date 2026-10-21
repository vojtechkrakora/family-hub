# Synology Container Manager

Use **compose.synology.yaml as a standalone project**, not as an override for
compose.yaml. It enables live transport, school and calendar sources explicitly.
Secrets are read from a read-only directory mount, never injected into the
container environment or copied into the image. No Python installation or startup
helper is required on the NAS. Actual Synology deployment remains unverified;
Compose validation and container file-based configuration are tested separately.

## Prepare the project

1. Copy or clone the repository into a dedicated NAS folder, for example
   `/volume1/docker/homeboard`. Keep the Dockerfile, requirements and homeboard
   source directory alongside the Compose file.
2. Separately copy the existing private `.local/bakalari.json` and
   `.local/calendar.json` into `.local` beneath that project folder. These files
   are deliberately absent from Git. Do not paste their contents into the
   Container Manager YAML editor. Never copy `.venv` or runtime caches.
3. No SSH, `sudo`, or ownership change is needed. The Compose project mounts
   only these two files as read-only. It runs as root only to read files that
   File Station may assign to an arbitrary NAS UID. The only retained Linux
   capability is `DAC_OVERRIDE`, which permits that read; the container cannot
   write the mounted files or its own filesystem, and `no-new-privileges` is
   enabled. Keep the project folder private in File Station and do not share it
   with other NAS users. Keep a private backup: deleting the project folder
   would delete its secrets.
4. Create `.env` in the project folder with **non-secret settings only**:

   ```dotenv
   HOMEBOARD_BIND_IP=192.168.1.100
   HOMEBOARD_PORT=8091
   WALKING_MINUTES=1
   DRESSING_MINUTES=10
   SHOES_MINUTES=3
   ```

   Replace the example IP with the NAS's actual private LAN address. Check that
   port 8091 is free; if occupied, choose another unused port for Homeboard.
   Never use port 8000 or stop another application to free a port.

## Create the Container Manager project

In **Container Manager → Project → Create**, name the project `homeboard`, select
that repository folder as its **Path**, and import the contents of
`compose.synology.yaml` as the project's Compose YAML. Container Manager may save
this as `docker-compose.yml`; this is expected. Use this definition alone.
Build and start the project. These controls are documented in
[Synology's Project guide](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project).

Compose reads `.env` from the project folder. If your Container Manager version
requires settings directly in its YAML editor, replace the bind-IP expression
with the actual private NAS IP; leave configuration file paths and live source
selectors intact. No credentials belong in YAML.

Open `http://<nas-lan-ip>:8091` and log in as `homeboard` with the existing
Homeboard password. `/health` is public; the dashboard must return 401 without
credentials. Verify that school and calendar report connected, not demo data.
Allow the first calendar refresh up to 25 seconds. The health check verifies the
web service; each integration has its own status on the dashboard.

The service restarts automatically after a NAS restart. Rebuilding or recreating
it retains live sources and protection because the Compose definition contains
file paths and the files remain on the NAS. After editing private configuration,
restart the Homeboard project to reload it. No startup helper is needed.

## Troubleshooting and limits

- Missing `.local`: the mount fails instead of silently creating a new directory.
- Missing, malformed or unreadable JSON: application startup fails with a
  sanitized configuration error; it never silently switches to mock data.
- Both configuration files are required in this household deployment. The school
  file also provides the dashboard login password.
- Do not paste raw files or full container diagnostics into issues/chat.
- Cache contents remain in memory and are lost on restart.
- LAN HTTP does not encrypt Basic authentication. Use a trusted HTTPS reverse
  proxy for encrypted household access; do not forward this port from the router.
