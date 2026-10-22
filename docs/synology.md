# Synology Container Manager

Use **compose.synology.yaml as a standalone project**, not as an override for
the local-development compose.yaml. When copying it into the Synology project
folder, rename it to **compose.yaml** because Container Manager expects that
filename. It enables live transport, school and calendar sources explicitly.
Secrets are read from two read-only file mounts, never injected into the
container environment or copied into the image. No Python installation or startup
helper is required on the NAS. Actual Synology deployment remains unverified;
Compose validation and container file-based configuration are tested separately.

The default project publishes port **8091** on the NAS network interfaces.
No `.env` file or NAS IP setting is required. An existing `.env` from local
development does not affect this standalone definition, including its port and
live source selection.

## Prepare the project

1. Copy or clone the repository into a dedicated NAS folder, for example
   `/volume1/docker/homeboard`. Keep the Dockerfile, requirements and homeboard
   source directory alongside the Compose file.
   Copy the complete `homeboard/static` directory, including its `icons`
   subdirectory. The image build checks that required frontend assets exist.
2. Separately copy the existing private `.local/bakalari.json` and
   `.local/calendar.json` from the development computer directly into the NAS
   project folder, preserving the filenames. They must sit beside `Dockerfile`
   and the Synology `compose.yaml`; no hidden or additional folder is needed. Both
   filenames are excluded from Git and Docker build context. Do not paste file
   contents into the Container Manager YAML editor. Never copy `.venv` or
   runtime caches.
3. No SSH, `sudo`, or ownership change is needed. The Compose project mounts
   only these two files as read-only. It runs as root only to read files that
   File Station may assign to an arbitrary NAS UID. The only retained Linux
   capability is `DAC_OVERRIDE`, which permits that read; the container cannot
   write the mounted files or its own filesystem, and `no-new-privileges` is
   enabled. Keep the project folder private in File Station and do not share it
   with other NAS users. Keep a private backup: deleting the project folder
   would delete its secrets.
4. In Container Manager, check that no other container publishes port 8091.
   If occupied, change only the first number in `"8091:8091"` in the project
   YAML to another unused port, and use that port in the browser. Never use
   port 8000 or stop another application to free a port. Otherwise leave the
   supplied YAML unchanged. Preparation durations can also be edited directly
   in its `environment` section; all settings have working defaults.

## Create the Container Manager project

Before creating the project, copy `compose.synology.yaml` from the repository to
the NAS project folder **as `compose.yaml`**. Do not copy the repository's local
`compose.yaml`; that definition uses mock integrations and different local
settings.

In **Container Manager → Project → Create**, name the project `homeboard` and
select that folder as its **Path**. Container Manager loads its `compose.yaml`.
Use this definition alone.
Build and start the project. These controls are documented in
[Synology's Project guide](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project).

No additional environment settings are required. No credentials belong in YAML.

Open `http://<nas-lan-ip>:8091` directly on the TV. This household deployment sets
`HOMEBOARD_AUTH_MODE: disabled`, so the page, assets and API require no login.
This is also the application default: older project YAML without that variable
needs no edits when updating the application.
Anyone with network access to this port can see the household dashboard.
School passwords and private calendar URLs remain server-side. Verify that
school and calendar report connected, not demo data.
Allow the first calendar refresh up to 25 seconds. The health check verifies the
web service; each integration has its own status on the dashboard.

The service restarts automatically after a NAS restart. Rebuilding or recreating
it retains live sources and the chosen login mode because the Compose definition contains
file paths and the files remain on the NAS. After editing private configuration,
restart the Homeboard project to reload it. No startup helper is needed.

## Troubleshooting and limits

- Healthy container but unreachable dashboard: the internal health check does
  not test published ports. Confirm the project YAML contains `"8091:8091"`
  and the container details show host port 8091 mapped to container port 8091.
  After changing ports, apply the project YAML and recreate the container;
  restarting an existing container retains its previous port mapping. Older
  definitions used `HOMEBOARD_BIND_IP`, which could bind only to loopback.
  If the mapping is correct, check that the DSM firewall permits TCP 8091 from
  the household LAN. `/health` should be reachable before opening the dashboard.
- `RuntimeError: Directory '/app/homeboard/static' does not exist`: check in
  File Station that the project folder contains `homeboard/static/index.html`
  and all sibling assets from the repository. Rebuild the project image and
  recreate the container using Container Manager; restarting the old container
  does not copy new source files. Remove any manually added mount targeting
  `/app` or `/app/homeboard`, which would hide the files built into the image.
  The supplied Synology Compose mounts only the two private JSON files.
- Missing `bakalari.json` or `calendar.json` beside `Dockerfile`: the mount or
  application startup fails instead of silently switching to demo data. Upload
  both individual files into the project folder before building the project.
- Missing, malformed or unreadable JSON: application startup fails with a
  sanitized configuration error; it never silently switches to mock data.
- Bakaláři unexpectedly switch to mock data or fail after recreating the
  project: verify that the NAS file named `compose.yaml` is the content of the
  repository's `compose.synology.yaml`, not its local-development `compose.yaml`.
- Both configuration files are required in this household deployment. Keep the
  existing school JSON unchanged, including its dashboard password field; it is
  unused for access when authentication is disabled.
- Do not paste raw files or full container diagnostics into issues/chat.
- Cache contents remain in memory and are lost on restart.
- To restore login, set `HOMEBOARD_AUTH_MODE: basic` in the project environment
  and recreate the container. Login is then `homeboard` and the existing dashboard
  password. The Synology default is intended for a trusted household LAN; do not
  forward this port from the router.
