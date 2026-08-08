# Temporary AI/assistant SSH access

Scripts for giving an AI coding assistant (or any third party you don't want
holding your real login) a scoped, easy-to-revoke SSH account on a device
running this project — e.g. the Raspberry Pi driving the touchscreen UI.

Written so it's copy-pasteable into other projects: nothing here references
`philco` specifically, everything is controlled by `SERVICE_USER` at the top
of each script.

## Why this shape

- **Separate account, not your own login.** The assistant never sees your
  personal credentials.
- **Key-only, password locked.** `passwd -l` disables password auth entirely;
  the only way in is the dedicated keypair.
- **NOPASSWD sudo.** A password prompt on `sudo` doesn't add safety here —
  the assistant runs commands as discrete non-interactive SSH calls, so
  there's no terminal for a human to type a password into. Every command it
  runs already shows up in the chat/tool-call log for review, which is where
  the actual visibility comes from, not the sudo prompt.
- **Toggle, not create/destroy.** Enabling/disabling access is a one-line
  script that adds or empties `authorized_keys`. No user creation/deletion
  churn for routine on/off; `remove-service-account.sh` is there for when you
  want the account gone completely.

## One-time setup

1. On your own machine (not the Pi), generate a keypair dedicated to this
   purpose — don't reuse your personal key:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/<project>-agent-key -N "" -C "agent-temp-access"
   ```
2. Copy `setup-service-account.sh` to the target device and run it as a user
   with sudo rights, passing the public key:
   ```bash
   sudo ./setup-service-account.sh "$(cat ~/.ssh/<project>-agent-key.pub)"
   ```
   Override the account name if you don't want the default `claude-agent`:
   ```bash
   SERVICE_USER=my-agent sudo -E ./setup-service-account.sh "ssh-ed25519 AAAA..."
   ```
   This creates the locked-password sudo account, stages the public key at
   `/home/$SERVICE_USER/agent_pubkey.txt` (not live yet), and installs
   `/usr/local/sbin/agent-access-on.sh` / `agent-access-off.sh`.

   > Needs a few KB of free disk space for the account/home dir. If
   > `adduser`/`tee` fail with "No space left on device", free some space
   > first (see [scripts/pi-maintenance/](../pi-maintenance/) if this
   > keeps happening) — a partially-created account/sudoers file can leave
   > the system in a broken state, so don't skip the `visudo -c` check the
   > script runs.

## Day to day

Enable before a session:
```bash
sudo /usr/local/sbin/agent-access-on.sh
```

Disable when done — this blocks the *next* login attempt immediately:
```bash
sudo /usr/local/sbin/agent-access-off.sh
```

To also kill any session that's already connected:
```bash
sudo pkill -u claude-agent   # or your SERVICE_USER
```

## Full teardown

Remove the account, its sudoers entry, and home directory entirely:
```bash
sudo ./remove-service-account.sh
```

## Reusing this in another project

Copy this whole `remote-access/` directory into the new project, generate a
fresh keypair for it, and run `setup-service-account.sh` on the new device.
Nothing needs editing unless you want a different `SERVICE_USER` name.
