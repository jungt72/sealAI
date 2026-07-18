#!/bin/bash
# Read-only health sweep for sealAI's own guard mechanisms. Never starts,
# stops, enables, or modifies anything -- pure observation, mirroring
# docker_disk_guard.py's own "never removes data" stance.
#
# There is no outbound mail/push transport configured on this host (no
# sendmail/postfix/msmtp) -- this is a pull-style check: it writes a clear
# OK/WARN status to its log and exits non-zero on any WARN, for whoever
# checks or greps the log. It does not page anyone by itself.
set -uo pipefail  # deliberately not -e: one failed check must not skip the rest

STATUS=0
now_epoch=$(date +%s)

warn() { echo "WARN: $*"; STATUS=1; }
ok()   { echo "OK:   $*"; }

# --- 1. Docker disk guard: the systemd timer must be enabled and active, and
#        its state dir must have been touched recently (corroborates it's
#        actually doing work, not just "loaded"). 2026-07-18: found disabled
#        with the legacy cron path silently retired to a no-op shim -- this
#        check exists specifically to catch that class of silent guard death.
# is-enabled/is-active print the actual state on stdout even when they exit
# non-zero (e.g. "disabled", "inactive") -- do not add "|| echo unknown" here,
# that would append a second line to the very state the exit code reflects.
timer_enabled=$(systemctl is-enabled sealai-docker-disk-guard.timer 2>/dev/null)
timer_active=$(systemctl is-active sealai-docker-disk-guard.timer 2>/dev/null)
[ -z "$timer_enabled" ] && timer_enabled="unknown"
[ -z "$timer_active" ] && timer_active="unknown"
if [ "$timer_enabled" != "enabled" ] || [ "$timer_active" != "active" ]; then
  warn "sealai-docker-disk-guard.timer is enabled=$timer_enabled active=$timer_active (expected enabled+active) -- the disk guard is not actually scheduled to run"
else
  ok "sealai-docker-disk-guard.timer is enabled and active"
fi

guard_state_dir="/var/lib/sealai-disk-guard"
if [ -d "$guard_state_dir" ]; then
  mtime=$(stat -c %Y "$guard_state_dir" 2>/dev/null || echo 0)
  age_min=$(( (now_epoch - mtime) / 60 ))
  if [ "$age_min" -gt 180 ]; then
    warn "docker-disk-guard state dir not updated in ${age_min}m (expected hourly, allowed 180m)"
  else
    ok "docker-disk-guard state dir last updated ${age_min}m ago"
  fi
else
  warn "docker-disk-guard state dir ${guard_state_dir} does not exist -- guard has never run"
fi

# --- 2. Any sealai-* systemd unit that is unexpectedly failed (not masked) --
# Masked units are a deliberate terminal state, not a live failure signal.
while read -r unit; do
  [ -z "$unit" ] && continue
  load_state=$(systemctl show -p LoadState --value "$unit" 2>/dev/null)
  [ "$load_state" = "masked" ] && continue
  warn "systemd unit $unit is active+failed (LoadState=$load_state)"
done < <(systemctl list-units 'sealai-*' --all --state=failed --no-legend --plain 2>/dev/null | awk '{print $1}')

# --- 3. Known gap: public port guard has no working implementation ---------
port_guard_state=$(systemctl show -p LoadState --value sealai-public-port-guard.service 2>/dev/null)
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
if [ "$port_guard_state" = "masked" ]; then
  if [ -x "${script_dir}/public-port-guard.sh" ]; then
    ok "public-port-guard.sh now exists and is executable, but the unit is still masked -- consider re-enabling"
  else
    warn "public-port-guard.service is masked (deliberate since 2026-07-18) AND ops/public-port-guard.sh does not exist -- known coverage gap, not auto-fixed by this check"
  fi
else
  ok "public-port-guard.service is not masked (state: $port_guard_state) -- verify separately that it actually started successfully"
fi

# --- 4. Weekly rotation cron jobs: log freshness (only once they're due) ----
check_weekly_log() {
  local name="$1" log="$2" max_age_days="$3"
  if [ ! -f "$log" ]; then
    ok "$name: no log yet ($log) -- fine if its first scheduled run hasn't passed yet"
    return
  fi
  local mtime age_days
  mtime=$(stat -c %Y "$log" 2>/dev/null || echo 0)
  age_days=$(( (now_epoch - mtime) / 86400 ))
  if [ "$age_days" -gt "$max_age_days" ]; then
    warn "$name: log $log not updated in ${age_days}d (expected weekly)"
  else
    ok "$name: log updated ${age_days}d ago"
  fi
}
check_weekly_log "rotate_env_rollbacks" "/home/thorsten/rotate-env-rollbacks.log" 9
check_weekly_log "rotate_docker_images" "/home/thorsten/rotate-docker-images.log" 9

echo "----"
if [ "$STATUS" -eq 0 ]; then
  echo "guard-health: all checks OK"
else
  echo "guard-health: at least one WARN above (no mail/push transport configured on this host -- pull-only, check this log)"
fi
exit "$STATUS"
