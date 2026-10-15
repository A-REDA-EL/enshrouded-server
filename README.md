# Enshrouded server for Hetzner

A private Steam/PC server with eight player slots, persistent world data,
separate Admin/Friends passwords, UDP readiness checks, rotated container logs,
restart after process exits/reboots, verified backups and explicit updates.
Startup refuses missing or unprotected configuration, including direct Compose
starts, so a configuration error cannot silently create a public server.

Researched on **15 October 2026**. Uses the community container release
**v1.0.7-proton**, published today, pinned by SHA-256 digest. This is the
**container version**, not the game version. The maintenance service downloads
the current **public** Enshrouded Dedicated Server (Steam app **2278520**) using
DepotDownloader. The container includes **GE-Proton 11-7** for the Windows binary.
No Steam account/password is needed. [Image source](https://github.com/indifferentbroccoli/enshrouded-server-docker/blob/main/Dockerfile.proton),
[release](https://github.com/indifferentbroccoli/enshrouded-server-docker/releases/tag/1.0.7),
[downloader](https://github.com/SteamRE/DepotDownloader).

## Hardware and connection

Use **Linux x86-64/amd64** with a **public IPv4**, Docker Engine, Compose v2
(2.20+ recommended), Python 3.10+ and systemd. Ubuntu 24.04 LTS is a suitable
target. **Hetzner CAX/ARM and IPv6-only servers do not fit this deployment.**

Keen's published baseline is 16 GB host RAM, 30 GB free SSD space, six fast
CPU cores at about 3.2 GHz for 4–6 players; for 16 players, eight faster cores at
about 3.7 GHz. These are older published recommendations, **not 1.0 benchmarks**.
For this eight-slot setup, allow **16 GB RAM, 6–8 fast cores and 60 GB free SSD**
to leave installation/update/backup headroom. A cloud vCPU is a hardware thread;
six vCPUs do not guarantee six dedicated physical cores. Dedicated CPU resources
give more predictable performance than shared CPU. The game has no GPU requirement.
[Keen specifications](https://enshrouded.zendesk.com/hc/en-us/articles/16055628734109-Recommended-Server-Specifications),
[Hetzner server types](https://docs.hetzner.com/cloud/servers/overview/).

Keen recommends about **2 Mbps in each direction per active player**:

| Active players | Baseline upload and download | Suggested headroom, each way |
| --- | --- | --- |
| 4 | 8 Mbps | 15–20 Mbps |
| 6 | 12 Mbps | 20–25 Mbps |
| 8 | 16 Mbps | 25–35 Mbps |
| 16 | 32 Mbps | 50+ Mbps |

Headroom is an operational recommendation, not a measured requirement. Hetzner
says Cloud commonly delivers 300–500 Mbps without a bandwidth guarantee, which
normally exceeds this baseline. Check your plan's transfer allowance too:
16 Mbps sustained outbound is about **7.2 GB/hour**, a conservative sizing
calculation rather than measured game traffic. Choose a region close to your
friends; aim for under roughly 80 ms round-trip latency and minimal packet loss.
[Bandwidth requirement](https://enshrouded.zendesk.com/hc/en-us/articles/16055628734109-Recommended-Server-Specifications),
[Hetzner network](https://docs.hetzner.com/cloud/technical-details/faq/).

## Install on the server

1. Install Docker Engine and the Compose plugin using Docker's instructions for
   your OS: [Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
   [Debian](https://docs.docker.com/engine/install/debian/).
   Install `python3`, enable Docker at boot, and check architecture:

   ```bash
   sudo apt-get update
   sudo apt-get install -y python3
   sudo systemctl enable --now docker
   uname -m                    # must show x86_64
   sudo docker compose version
   ```

2. Copy **this entire folder**, including `compose.yaml`, `server.py`, `scripts/`
   and `systemd/`, to `/opt/enshrouded` on the host. For example, from the local
   project folder (replace the IP and SSH user):

   ```bash
   ssh root@YOUR_PUBLIC_IPV4 'mkdir -p /opt/enshrouded'
   rsync -av --exclude='.git' --exclude='.env' --exclude='server-data' \
     --exclude='backups' --exclude='credentials.txt' --exclude='__pycache__' \
     ./ root@YOUR_PUBLIC_IPV4:/opt/enshrouded/
   ```

3. On Hetzner, run:

   ```bash
   cd /opt/enshrouded
   sudo python3 server.py install --name "Embervale with Friends" --players 8
   sudo python3 server.py status
   sudo cat credentials.txt
   ```

   The first download can take several minutes. `install` checks the host,
   generates random passwords, preserves any existing configuration, creates a
   backup, downloads the game and waits up to ten minutes for a successful query.
   `credentials.txt` is readable only by its owner; give friends only the
   **Friends password**. The Admin password allows kicking/banning. Friends can
   build, access containers and extend bases. Passwords grant group permissions;
   there is no separate account whitelist in this configuration.
   [Group permissions](https://enshrouded.zendesk.com/hc/en-us/articles/19191581489309-Server-Roles-Configuration).

   To change the name, slots, difficulty or passwords later, stop the server,
   edit `server-data/enshrouded_server.json`, and start it. Keep the configured
   save path, bind IP and port. Running `setup` again preserves the existing
   config. `credentials.txt` is an initial record; the JSON is authoritative
   after edits or a restore. Optional resource/image overrides go in `.env`
   copied from `.env.example`; the default RAM limit is 12 GiB on a 16 GB host.

## Firewall: required before friends connect

For a **Hetzner Cloud Firewall**, add these inbound rules and attach it to the
server. Retain existing access rules for other applications.

| Protocol | Destination port | Source | Purpose |
| --- | --- | --- | --- |
| TCP | Your SSH port (usually 22) | Your administrator IP/CIDR | SSH access |
| UDP | 15637 | `0.0.0.0/0`, or friends' public IPv4 CIDRs | Game/query traffic |
| ICMP | — | `0.0.0.0/0` | Ping/network diagnostics, optional |

Leave **outbound unrestricted** for Steam authentication, content downloads,
DNS and registration. A Hetzner **Robot dedicated server** uses a different
firewall interface: allow the same game port and the required return/outbound
traffic there. Do not replace your existing SSH rule or flush the firewall.
[Cloud firewall behavior](https://docs.hetzner.com/cloud/firewalls/faq/).

This setup publishes **UDP 15637**, matching the official default; do not open
TCP 15637 or old game port 15636 just because an older guide lists them. No
web proxy or load balancer is needed. The server listens on `0.0.0.0` **inside
the container**; do not put your Hetzner public IP into its JSON bind setting.
[Official port/IP configuration](https://enshrouded.zendesk.com/hc/en-us/articles/16055441447709-Dedicated-Server-Configuration).

Docker-published ports can bypass UFW's normal input rules. Use the Hetzner
firewall as the external access control; any additional host firewall must allow
the Docker forwarding path. A UFW `allow` command alone does not prove Docker
traffic is restricted as intended. [Docker firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## Join with friends

1. Everyone updates Enshrouded in Steam to the same public version.
2. Open **Steam → View → Game Servers → Favorites → +**.
3. Add **`YOUR_PUBLIC_IPV4:15637`**.
4. Open Enshrouded → **Play/Join**, enable the dedicated-server filter, select
   the favorite server and enter the Friends password.

The public IP is the address players use; it is not required in Compose.
[Keen's favorite-server instructions](https://enshrouded.zendesk.com/hc/en-us/articles/16454683440541-Favorite-Server-via-IP).

From **another machine outside Hetzner**, check public query reachability:

```bash
python3 scripts/query.py YOUR_PUBLIC_IPV4 15637 --timeout 5
```

A successful result shows server name, player count and password protection.
It verifies the UDP query path, not a complete player login. A TCP port-checking
website or `curl` cannot test this UDP service. On the host:

```bash
sudo docker compose exec -T enshrouded python3 /opt/enshrouded/query.py 127.0.0.1
sudo python3 server.py logs
```

## Backups and updates

All commands below run from `/opt/enshrouded` on the host with `sudo`.

```bash
sudo python3 server.py backup              # stop, archive, verify, restart
sudo python3 server.py update              # backup, download public build, start
sudo python3 server.py stop
sudo python3 server.py start
sudo python3 server.py status
```

Backups briefly disconnect players. They include **world saves and server
configuration**, with passwords, and retain the latest **14 successful archives**
in `backups/`. A stopped server stays stopped after a backup. Backup failures
attempt to restart a previously running server; download failures leave the game
stopped so a partially updated installation cannot start. Retry `update` after
fixing the error. Maintenance commands use a host lock to prevent overlap;
use this tool rather than issuing simultaneous manual Compose operations.

Ordinary restarts do **not** update game files. After a client patch, arrange a
maintenance window and run `update`. This changes the game build, not the pinned
container. For a future container upgrade, review the upstream release and set
`ENSHROUDED_IMAGE` to its tag plus verified digest in `.env`, then run
`sudo docker compose pull enshrouded` followed by `sudo python3 server.py update`.

Enable daily backups at **05:00–05:05 UTC** (brief downtime):

```bash
sudo cp systemd/enshrouded-backup.service systemd/enshrouded-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now enshrouded-backup.timer
sudo systemctl list-timers enshrouded-backup.timer
sudo journalctl -u enshrouded-backup.service
```

The units assume `/opt/enshrouded`; edit both paths in the service if installed
elsewhere. Monitor the service for failed backups. Copy archives to a separate
machine/storage service, for example `rsync` over SSH; on-server copies do not
survive loss of the host/disk. They contain passwords, so keep them private.

Restore a selected backup:

```bash
sudo python3 server.py restore backups/enshrouded-TIMESTAMP.tar.gz --yes
```

Restore validates and stages the archive, creates a safety backup of the current
world, then replaces saves/config and restarts only if previously running. It
also restores that archive's passwords. It does **not** roll back game binaries;
new saves may not work with an older game build. Archives above 10 GiB or with
links/unsafe paths are rejected. Never delete `server-data/` to troubleshoot.

World saves, configuration and installation live in `server-data/`. Character
progression is stored on each player's client, so friends should protect their
own Steam saves too. Keen documents five-minute world autosaves; a hard crash can
lose progress since the last save. The two-minute stop allowance lets the
container attempt a graceful shutdown, but cannot guarantee a final flush.
[Dedicated server FAQ](https://enshrouded.zendesk.com/hc/en-us/articles/16056312924957-Dedicated-Server-FAQ).

## Troubleshooting and verification limits

- **Healthy locally, unreachable outside:** verify the public IPv4, attached
  Hetzner firewall, UDP rule and host forwarding rules. `healthy` is a container
  loopback query, not proof of public reachability.
- **Starting/unhealthy:** inspect `sudo docker compose logs --tail 200 enshrouded`
  and `server-data/logs/engine.log`. Check memory, disk and game/config errors.
  Docker restarts exited processes; health failures alone do not trigger a
  restart. Investigate persistent unhealthy status and use `server.py restart`
  after fixing the cause. The query probe supports single-packet A2S_INFO replies
  and Steam challenges; a future protocol change may require updating it.
- **Version mismatch after a patch:** update every client and run `server.py update`.
  Check download output for success; do not assume a running container means the
  latest game build was downloaded.
- **Lag despite ample bandwidth:** inspect `sudo docker stats`, CPU steal time
  (`top`), available RAM/disk and packet loss. Shared CPU contention and distance
  can dominate game performance. Reduce slots or move to faster/dedicated CPU.
- **Reboot:** Docker must be enabled. `restart: unless-stopped` recovers a running
  server; one deliberately stopped before reboot needs `server.py start`.
- **Logs/disk:** Docker logs are rotated; backup maintenance removes game logs
  in `logs/backup` older than 14 days. Watch free disk and failed timer runs.

Local verification:

```bash
python3 -m unittest discover -s tests -v
docker compose config --quiet
```

The tests exercise real UDP challenge replies and real archive creation/restore,
with the Docker lifecycle boundary simulated. Compose and registry metadata can
be verified locally. **A Linux x86-64 startup, external query and real Steam
player login must be checked on the target server before calling it live.**
