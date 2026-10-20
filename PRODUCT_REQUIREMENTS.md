# Homeboard — Family Information Dashboard

## Project Overview

Homeboard is a self-hosted family information dashboard designed to run on a Synology NAS and be displayed on a 55" LG Smart TV (LG 55SK8100PLA, webOS).

The goal is to create a reliable, fully automated morning dashboard that helps the family prepare for school and daily activities.

Every school morning, the TV should automatically turn on, display the Homeboard web application in fullscreen mode, continuously update relevant information, and turn off at a configured time.

The application should also be accessible from mobile phones and desktop browsers within the local network.

The project is intended for personal household use, not as a commercial SaaS product.

## Core Features

### 1. Public Transportation

This is the highest-priority dashboard feature.

- Display the next bus departure from **Planá nad Lužnicí, Lipová alej** to **Planá nad Lužnicí, náměstí**, Czech Republic.
- Show a large, clearly visible countdown in minutes.
- Highlight upcoming departures using configurable warning thresholds.
- Display scheduled departure times and real-time delays when available.
- Ideally, show the current GPS location of the approaching bus.
- Investigate available transportation data sources, particularly JIKORD/IDESKA and relevant Czech public transport APIs.
- Do not assume that real-time vehicle location APIs are publicly accessible.
- Support fallback to scheduled departure data.
- Allow configuration of walking time to the bus stop and display a separate "time to leave home" countdown.

### 2. Bakaláři School Integration

Integrate with the Czech Bakaláři school information system.

Required functionality:

- Display homework assignments and deadlines.
- Highlight homework due today or tomorrow.
- Show relevant timetable changes.
- Optionally display important school announcements.
- Support multiple children/accounts in the future.
- Investigate existing unofficial Bakaláři APIs or Python clients.
- Keep credentials securely on the server.
- Cache previously retrieved data and display the last successful synchronization time.

### 3. Family Calendar

Integrate with Google Calendar or a configurable iCalendar/ICS feed.

- Display today's events.
- Show event times and titles.
- Support multiple family calendars.
- Highlight upcoming appointments.
- Optionally display important events for tomorrow.

### 4. Automated LG TV Control

Target television: **LG 55SK8100PLA (webOS)**.

Desired behavior:

- Automatically power on every school morning at a configurable time.
- Launch the Homeboard URL in the TV's web browser.
- Display the dashboard fullscreen if technically supported.
- Automatically power off at a configurable time.
- Support manual power-on/power-off commands.

Investigate:

- Wake-on-LAN and LG network power-on capabilities.
- LG webOS WebSocket APIs and pairing.
- Remote browser/application launching with a specific URL.
- Reliability after overnight standby.
- Limitations of the TV's older webOS browser.

Prefer using the existing TV without additional hardware.

If native automation proves unreliable, evaluate an external HDMI kiosk device with HDMI-CEC support.

Do not assume these capabilities work until tested on the actual TV.

### 5. Dashboard UI

The UI must be optimized for a 55" television viewed from several meters away.

Design principles:

- Large typography and high contrast.
- Clean, modern appearance.
- Minimal visual clutter.
- Transportation countdown as the most prominent element.
- Homework and family calendar clearly separated.
- Current date and time visible.
- Responsive design for mobile and desktop.
- Prefer a dark theme.
- Automatic data refresh without page reload.
- Clear indication when external data is unavailable or outdated.

The dashboard should function without keyboard or mouse interaction during normal operation.

## Proposed Technical Architecture

Preferred stack:

- **Backend:** Python 3 + FastAPI
- **Frontend:** HTML/CSS/TypeScript or lightweight JavaScript
- **Deployment:** Docker Compose on Synology NAS
- **Storage:** SQLite for settings and cached data
- **Integrations:** Separate modules for transportation, Bakaláři and calendars
- **TV control:** Separate LG webOS controller/service
- **Scheduling:** Lightweight application scheduler or scheduled tasks

Keep the architecture modular but avoid unnecessary complexity.

This is a small personal application. Do not introduce Kubernetes, microservices, message brokers, or other heavy infrastructure without a concrete need.

Expose a simple REST API for the frontend.

## Non-Functional Requirements

- Run continuously on a Synology NAS.
- Low CPU and memory usage.
- Reliable unattended operation.
- Secure handling of credentials and API tokens.
- Configuration through environment variables or configuration files.
- Local-network-first deployment.
- Graceful handling of internet outages and third-party API failures.
- Structured logging and basic health checks.
- Correct handling of the Europe/Prague timezone, including daylight saving time.
- Easy local development on macOS.
- Support automated tests for important business logic, especially bus countdown calculations.

## Implementation Strategy

Develop incrementally.

**Phase 1 — Foundation**
- Establish project structure and Docker Compose configuration.
- Implement FastAPI backend and basic frontend.
- Create a mock-data dashboard.
- Make the dashboard accessible from devices on the local network.

**Phase 2 — LG TV Proof of Concept**
- Test Wake-on-LAN.
- Test webOS pairing and remote commands.
- Test launching the dashboard URL.
- Test scheduled power-on and power-off.
- Document actual capabilities and limitations.

**Phase 3 — Transportation**
- Research verified bus timetable data sources.
- Implement departure lookup and countdown.
- Add walking-time and departure warnings.
- Investigate live GPS location integration.

**Phase 4 — Bakaláři**
- Implement authentication and homework retrieval.
- Add timetable changes and school announcements where supported.

**Phase 5 — Calendar**
- Integrate Google Calendar or ICS feeds.
- Implement daily agenda visualization.

**Phase 6 — Hardening**
- Improve error handling, caching, logging and tests.
- Optimize the UI for the actual TV browser.
- Validate unattended morning operation.

## Guidelines for AI Coding Agents

Act as a pragmatic senior software engineer and architect.

- Prefer simple and maintainable solutions.
- Do not invent API endpoints, undocumented capabilities or external data availability.
- Verify external integrations before implementing them.
- Clearly distinguish confirmed functionality from assumptions.
- Implement small, testable increments.
- Use interfaces/adapters for integrations so mock implementations can be replaced with real ones.
- Provide concise explanations for architectural decisions.
- Avoid unnecessary dependencies and abstractions.
- Maintain a README with setup instructions and project status.
- Document technical uncertainties and known limitations.
- Do not implement the entire system at once.

## Initial Task

Start by reviewing these requirements and proposing:

1. A minimal project architecture.
2. The initial repository structure.
3. The first working proof of concept.
4. The main technical risks and how to validate them.

Prioritize getting a basic Homeboard dashboard running locally and establishing whether the LG television can be controlled reliably.

**Do not start implementing all integrations immediately. First agree on the MVP scope and technical approach.**
