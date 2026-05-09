# Gate-Tracker-Kinrise

Deployment notes

Two-Pi setup

 - Configure each Raspberry Pi to run one instance of the watcher with a device id.
 - For example, Pi A (entrance) should use `DEVICE=pi-entrance` and Pi B (exit) should use `DEVICE=pi-exit`.

Steps

1. Copy the repo to both Pis.
2. On the entrance Pi, edit `/etc/gate-tracker/config.json` to set the correct GPIO pins for the entrance buttons and ensure each entrance button has `"device": "pi-entrance"`.
3. On the exit Pi, set `"device": "pi-exit"` for exit buttons and configure GPIO pins accordingly.
4. Enable the systemd service (adjust `Environment=DEVICE=` in `systemd/gate-tracker-watcher.service` or override via a drop-in) and start it on each Pi.

Example systemd override to set device per machine:

Create `/etc/systemd/system/gate-tracker-watcher.service.d/override.conf` with:

```
[Service]
Environment=DEVICE=pi-entrance
```

On the exit Pi set `DEVICE=pi-exit` instead, then run:

```
sudo systemctl daemon-reload
sudo systemctl restart gate-tracker-watcher.service
```