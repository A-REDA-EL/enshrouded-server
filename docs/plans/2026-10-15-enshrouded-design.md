# Enshrouded on Hetzner

Approved by the user on 2026-10-15 with recommended defaults.

Use the maintained indifferentbroccoli Proton image, pinned to v1.0.7-proton
and its verified registry digest. The Windows server runs on Linux x86-64;
Hetzner ARM/CAX and IPv6-only hosts are unsuitable for this setup.

Persist the entire installation under server-data. Generate separate nonempty
Admin and Friends group passwords and disable the image's config generation.
Allow eight players by default and publish UDP 15637 on IPv4. Do not update game
files during ordinary restarts. Use a separate maintenance service to download
the public dedicated-server build anonymously and fail on download errors.

Use an actual UDP Steam query for readiness. Docker restarts exited containers;
an unhealthy container requires investigation and an explicit restart. Rotate
Docker logs and preserve the image's bounded previous engine logs.

Provide a standard-library Python management command with exclusive maintenance
locking. Backups stop the server, archive configuration and saves atomically,
verify the archive, then restart only if previously running. Keep 14 successful
archives. Updates back up first and leave a failed update stopped. Restores reject
unsafe archives, preserve the current state first, and require an explicit flag.
Provide a daily systemd backup timer with a documented short interruption.

Document hardware, bandwidth, firewall rules, installation, Steam favorites,
updates, restoration, off-host copies and troubleshooting. Verify Compose with
Docker, test real local UDP query/challenge responses, archive validation and
maintenance failure behavior. Live game and external connectivity verification
require the user's Hetzner host and a Steam client.
