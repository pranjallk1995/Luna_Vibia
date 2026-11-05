#!/usr/bin/env bash
# Get Vibia's playback working again when ffmpeg cannot reach WSLg's sound server, which
# shows up as "Nothing was written into output file". Runs on the WSL host.
#
# The usual cause: Docker starts Vibia at boot before WSLg has made its socket, finds the
# path missing, and creates a directory there. WSLg's sound server then cannot make the
# socket, and the container keeps a directory where the socket should be.
#
#   repair_audio.sh          repair if needed; does nothing when audio already works
#   repair_audio.sh --check  only report; changes nothing
#
# Exits 0 when audio works, 1 when it does not. The audio tests are silent.

set -u

cd "$(dirname "$(readlink -f "$0")")/.." || exit 1

SOCKET="${PULSE_SOCKET:-/mnt/wslg/PulseServer}"
SOCKET_WAIT_SECONDS="${REPAIR_SOCKET_WAIT_SECONDS:-20}"
HEALTH_WAIT_SECONDS="${REPAIR_HEALTH_WAIT_SECONDS:-120}"
# Lets the helper finish answering the MCP tool call before its container is replaced.
RECREATE_DELAY_SECONDS="${REPAIR_RECREATE_DELAY_SECONDS:-2}"
WSL="$(command -v wsl.exe || echo /mnt/c/Windows/system32/wsl.exe)"

say() { echo "$*"; }

mcp_container() { docker compose ps -q mcp 2>/dev/null; }

audio_works() {
  local container
  container="$(mcp_container)"
  [ -n "$container" ] || return 1
  timeout 15 docker exec "$container" ffmpeg -hide_banner -v quiet -nostdin \
    -f lavfi -i anullsrc=r=44100:cl=stereo -t 0.2 -f pulse -name "Luna Vibia audio check" check \
    >/dev/null 2>&1
}

distro() {
  local name="${WSL_DISTRO_NAME:-}"
  [ -n "$name" ] || name="$(wslpath -w / 2>/dev/null | awk -F'\\' '{print $4}')"
  echo "$name"
}

as_root() { timeout 30 "$WSL" -d "$(distro)" -u root -- "$@" 2>&1 | tr -d '\000'; }

restart_sound_server() { timeout 30 "$WSL" -d "$(distro)" --system -u root -- pkill pulseaudio 2>&1 | tr -d '\000'; }

wait_for_socket() {
  local waited=0
  until [ -S "$SOCKET" ]; do
    [ "$waited" -lt "$SOCKET_WAIT_SECONDS" ] || return 1
    sleep 1
    waited=$((waited + 1))
  done
}

wait_for_healthy() {
  local waited=0 state
  while [ "$waited" -lt "$HEALTH_WAIT_SECONDS" ]; do
    state="$(docker inspect "$(mcp_container)" --format '{{.State.Health.Status}}' 2>/dev/null)"
    [ "$state" = healthy ] && return 0
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

if audio_works; then
  say "Audio works: Vibia reached the sound server. Nothing to repair."
  exit 0
fi
say "Audio does not work: Vibia cannot reach the sound server."

if [ "${1:-}" = "--check" ]; then
  if [ -S "$SOCKET" ]; then say "$SOCKET is a socket, so Vibia's container probably needs recreating."
  elif [ -d "$SOCKET" ]; then say "$SOCKET is a directory where WSLg's socket should be."
  else say "$SOCKET does not exist."
  fi
  exit 1
fi

if [ -d "$SOCKET" ]; then
  if [ -n "$(ls -A "$SOCKET" 2>/dev/null)" ]; then
    say "FAILED: $SOCKET is a directory with files in it, so it was left alone. Check it by hand."
    exit 1
  fi
  say "Removing the empty directory at $SOCKET."
  as_root rmdir "$SOCKET"
  if [ -e "$SOCKET" ]; then
    say "FAILED: could not remove $SOCKET."
    exit 1
  fi
fi

if [ ! -S "$SOCKET" ]; then
  say "Restarting WSLg's sound server so it makes its socket."
  restart_sound_server
  if ! wait_for_socket; then
    say "FAILED: WSLg did not make $SOCKET. Run 'wsl --shutdown' from Windows and start WSL again."
    exit 1
  fi
fi
say "$SOCKET is a socket."

sleep "$RECREATE_DELAY_SECONDS"
say "Recreating Vibia's MCP container so it mounts the socket."
if ! docker compose up -d --no-deps --no-build --pull never --force-recreate mcp 2>&1; then
  say "FAILED: could not recreate Vibia's MCP container."
  exit 1
fi
if ! wait_for_healthy; then
  say "FAILED: Vibia's MCP container did not become healthy."
  exit 1
fi

if audio_works; then
  say "REPAIRED: Vibia reached the sound server. Try playing again."
  exit 0
fi
say "FAILED: Vibia still cannot reach the sound server. Run 'wsl --shutdown' from Windows and start WSL again."
exit 1
