# LG television validation plan

Target: LG 55SK8100PLA. All hardware behavior below is **unverified**.
This POC includes no remote control commands and does not turn the TV on or off.

## First manual browser test

1. Run Homeboard on the NAS or a computer bound to its private LAN IP.
2. Open `http://<server-lan-ip>:8091` in the television browser.
3. Check readability from the normal seating position, overscan, contrast and
   layout. Confirm the demo label is visible. Ask the children to identify the
   sun, clothing, shoes and bus stages without reading the labels. Check that
   the highlighted step and draining time blocks make sense from their seats.
4. Watch the countdown change and roll over to the next sample departure.
5. Stop the backend, verify the failure indication, restart it and verify recovery.
6. Leave the page open for at least an hour; check for sleep/screensaver behavior.
7. Test browser fullscreen manually if available; record actual behavior.

## Subsequent automation proof of concept

Before implementation, record TV firmware/webOS version, network connection
(Ethernet or Wi-Fi), available network wake settings and NAS networking details.
Keep MAC addresses, TV addresses and pairing keys in protected local configuration.
Verify current API/client documentation before choosing commands.

Test network power-on, pairing, power-off and URL launching separately. Then test
power-on after overnight standby and a complete morning cycle several times.
Record timestamps, setup, observed results and failure rate. Confirm school-day
and holiday scheduling requirements before adding a scheduler.

If native operation cannot meet reliability needs, evaluate an external HDMI
kiosk device and test its CEC behavior with this TV. Do not buy additional hardware
based only on assumed compatibility.

## Test record

| Capability | Result | Evidence |
| --- | --- | --- |
| Dashboard rendering on TV | Not tested | Actual TV required |
| Refresh and recovery on TV | Not tested | Actual TV required |
| Fullscreen | Not tested | Actual TV required |
| Network wake after overnight standby | Not tested | Actual TV required |
| Pairing and remote power-off | Not tested | Actual TV required |
| Launch browser with dashboard URL | Not tested | Actual TV required |
| Repeated unattended morning cycle | Not tested | Actual TV required |
