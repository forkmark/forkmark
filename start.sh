#!/bin/sh
# =============================================================
#  Forkmark — macOS / Linux Launcher
#  No Python, no Node required.
#  Requires: Docker Desktop (macOS) or Docker Engine (Linux)
# =============================================================
set -e

FM_PORT="${FM_PORT:-7700}"
FM_URL="http://localhost:${FM_PORT}"
COMPOSE_FILE="docker-compose.simple.yml"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
# Disable colours if not a terminal
if [ ! -t 1 ]; then RED=''; YELLOW=''; GREEN=''; CYAN=''; BOLD=''; RESET=''; fi

die() { printf "\n  ${RED}✗  %s${RESET}\n\n" "$1"; exit 1; }
info() { printf "  ${CYAN}%s${RESET}\n" "$1"; }
ok()   { printf "  ${GREEN}✓  %s${RESET}\n" "$1"; }
warn() { printf "  ${YELLOW}⚠  %s${RESET}\n" "$1"; }

# ── Detect OS and architecture ────────────────────────────────────────────────
detect_system() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    case "$OS" in
        Darwin) OS_NAME="macOS" ;;
        Linux)  OS_NAME="Linux" ;;
        *)      OS_NAME="$OS"   ;;
    esac
    case "$ARCH" in
        x86_64|amd64)   ARCH_NAME="x86_64" ;;
        arm64|aarch64)  ARCH_NAME="arm64"   ;;
        *)               ARCH_NAME="$ARCH"  ;;
    esac
}

# ── HTTP health check (curl → wget → PowerShell fallback) ────────────────────
http_ok() {
    if command -v curl >/dev/null 2>&1; then
        curl -sf --max-time 2 "$FM_URL/api/health" >/dev/null 2>&1
    elif command -v wget >/dev/null 2>&1; then
        wget -q --timeout=2 -O /dev/null "$FM_URL/api/health" >/dev/null 2>&1
    else
        # Last resort: /dev/tcp (bash only, not POSIX sh — skip silently)
        return 1
    fi
}

# ── Browser opener ────────────────────────────────────────────────────────────
open_browser() {
    if [ "$OS" = "Darwin" ]; then
        open "$FM_URL" 2>/dev/null &
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$FM_URL" 2>/dev/null &
    elif command -v gnome-open >/dev/null 2>&1; then
        gnome-open "$FM_URL" 2>/dev/null &
    else
        info "Open your browser and go to: $FM_URL"
    fi
}

# ── Docker install guidance ───────────────────────────────────────────────────
docker_install_hint() {
    warn "Docker not found."
    printf "\n"
    info  "Forkmark runs inside Docker — a free container runtime."
    printf "\n"
    if [ "$OS" = "Darwin" ]; then
        info "Install Docker Desktop for macOS:"
        info "  https://www.docker.com/products/docker-desktop/"
        info "  (or: brew install --cask docker)"
    else
        # Linux — detect distro
        if command -v apt-get >/dev/null 2>&1; then
            info "Install Docker on Debian/Ubuntu:"
            info "  curl -fsSL https://get.docker.com | sh"
            info "  sudo usermod -aG docker \$USER  && newgrp docker"
        elif command -v dnf >/dev/null 2>&1; then
            info "Install Docker on Fedora/RHEL:"
            info "  sudo dnf install -y docker && sudo systemctl enable --now docker"
            info "  sudo usermod -aG docker \$USER  && newgrp docker"
        elif command -v pacman >/dev/null 2>&1; then
            info "Install Docker on Arch:"
            info "  sudo pacman -S docker && sudo systemctl enable --now docker"
        else
            info "Install Docker: https://docs.docker.com/engine/install/"
        fi
        info ""
        info "After installing, run ./start.sh again."
    fi
    printf "\n"
    exit 1
}

# ── Find docker compose command ───────────────────────────────────────────────
find_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE="docker-compose"
    else
        die "Docker Compose not found. Update Docker Desktop to the latest version."
    fi
}

# ── Wait for health endpoint ──────────────────────────────────────────────────
wait_for_health() {
    MAX=45
    i=0
    printf "  Waiting for Forkmark"
    while [ $i -lt $MAX ]; do
        if http_ok; then
            printf "  ${GREEN}✓${RESET}\n"
            return 0
        fi
        printf "."
        sleep 2
        i=$((i + 1))
    done
    printf "\n"
    warn "Still starting — open $FM_URL manually if it doesn't open."
    return 1
}

# ── First-run .env setup ──────────────────────────────────────────────────────
ensure_env() {
    if [ -f ".env" ]; then return; fi
    printf "\n"
    info "First-run setup"
    printf "  %s\n" "─────────────────────────────────────────────"
    info "Forkmark can use an AI API key for LLM judge"
    info "scoring (OpenAI / OpenRouter). This is optional."
    printf "\n"
    printf "  API key (press Enter to skip): "
    read -r FM_API_KEY
    printf "\n"
    if [ -n "$FM_API_KEY" ]; then
        printf "OPENAI_API_KEY=%s\nFM_OPENAI_API_KEY=%s\n" \
            "$FM_API_KEY" "$FM_API_KEY" > .env
    else
        printf "# Add your API key here to enable LLM judge scoring:\n# OPENAI_API_KEY=sk-...\n" > .env
    fi
}

# ═════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════

detect_system

printf "\n"
printf "  ${BOLD}╔══════════════════════════════════════════════╗${RESET}\n"
printf "  ${BOLD}║  Forkmark  —  AI Workflow QA Platform       ║${RESET}\n"
printf "  ${BOLD}╚══════════════════════════════════════════════╝${RESET}\n"
printf "  Platform : %s / %s\n" "$OS_NAME" "$ARCH_NAME"
printf "  URL      : %s\n" "$FM_URL"
printf "\n"

# ── Check Docker installed ────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    docker_install_hint
fi

# ── Check Docker running ──────────────────────────────────────────────────────
if ! docker info >/dev/null 2>&1; then
    warn "Docker is installed but not running."
    printf "\n"
    if [ "$OS" = "Darwin" ]; then
        info "Open Docker Desktop from your Applications folder,"
        info "then wait for the whale icon in the menu bar."
    else
        info "Start Docker:  sudo systemctl start docker"
        info "(To start on boot: sudo systemctl enable docker)"
    fi
    printf "\n"
    printf "  Retry after starting Docker? [Y/n] "
    read -r RETRY
    case "$RETRY" in
        [nN]*) exit 1 ;;
    esac
    if ! docker info >/dev/null 2>&1; then
        die "Docker still not running. Start it and try again."
    fi
fi

# ── Find compose command ──────────────────────────────────────────────────────
find_compose

# ── First-run setup ───────────────────────────────────────────────────────────
ensure_env

# ── Start ─────────────────────────────────────────────────────────────────────
info "Starting Forkmark..."
info "(First run builds the image — ~2 min. Subsequent starts are instant.)"
printf "\n"

$COMPOSE -f "$COMPOSE_FILE" up --build -d || die "Docker Compose failed. See output above."

# ── Wait + open browser ───────────────────────────────────────────────────────
printf "\n"
wait_for_health
printf "\n"
printf "  ${GREEN}${BOLD}╔══════════════════════════════════════════════╗${RESET}\n"
printf "  ${GREEN}${BOLD}║  Forkmark is running!                       ║${RESET}\n"
printf "  ${GREEN}${BOLD}║  Open: %-38s║${RESET}\n" "$FM_URL"
printf "  ${GREEN}${BOLD}╚══════════════════════════════════════════════╝${RESET}\n"
printf "\n"
info "To stop Forkmark, run:  ./stop.sh"
printf "\n"

open_browser
