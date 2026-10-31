# Edge box (Phase 2): live capture on a Linux bridge

> **UNTESTED.** Written without the hardware. Nothing in this file has been run on a
> real bridge. Treat every step as a plan to verify, not a procedure to trust.

Scope: monitor only networks you own or are authorised to monitor, and tell the
people who share the network that traffic is inspected.

## What it is, in plain words

A small Linux box with two network ports sits **between** the router and the switch,
like a turnstile on a cable. Traffic passes through it; a copy is inspected by
Suricata. The devices on your network do not need any changes.

- **Passive (recommended first):** the box only watches. A failure cannot cut the
  network. Use a SPAN/mirror port or a network TAP if your switch has one.
- **Inline bridge:** the box forwards the traffic itself. A fault here can cut the
  network, which is why Phase 4 (bypass or fail-open) must exist before this mode.

## Steps (to verify on hardware)

1. Install Ubuntu Server or Debian on the box, with two NICs: `eth0` (WAN side,
   towards the router) and `eth1` (LAN side, towards the switch).
2. Create the bridge, with no IP on the bridge itself:

   ```bash
   sudo apt install -y bridge-utils ethtool
   sudo ip link add br0 type bridge
   sudo ip link set eth0 master br0
   sudo ip link set eth1 master br0
   sudo ip link set br0 up eth0 up eth1 up
   ```

3. Disable offloads, so Suricata sees real packet sizes:

   ```bash
   sudo ethtool -K eth0 gro lro tso gso off
   sudo ethtool -K eth1 gro lro tso gso off
   ```

4. Run Suricata on the bridge (`-i br0`) and write `eve.json`. Install Suricata from
   the distribution or the OISF PPA; the version must match the rules you load.
5. Ship the events to AEGIS with the bridge script in live mode (follow `eve.json`
   as it grows). `--flows` also sends flow records:

   ```bash
   python3 backend/app/services/capture/bridges/suricata_bridge.py \
     --api https://aegis.example --email <sensor-user> --flows \
     --file /var/log/suricata/eve.json
   ```

   The script reads the file once and exits today. Live follow mode (`tail -F`
   behaviour) is **not built yet**; it is the first thing to add in Phase 2.

## Still missing (do not run as production)

- Sensor authentication: the script logs in with a user account. A dedicated
  sensor key is Phase 4.
- Fail-open or bypass for inline mode: not built.
- Updates for the Suricata rules: not built.
- Storage limits on the box (`eve.json` rotation is left to logrotate).

## Checks to make on the real box

- `ethtool -k eth1 | grep -E 'gro|lro|tso|gso'` shows `off`.
- Suricata's stats in `eve.json` show packets on `br0` growing while a device browses.
- AEGIS `/api/v1/alerts` shows the test alert (for example, a known test signature).
