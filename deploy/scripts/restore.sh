#!/usr/bin/env bash
#
# MdbUP — ripristino di un backup cifrato age su PostgreSQL.
#
# Uso (host):
#   deploy/scripts/restore.sh backups/mdbup-20250101T030000Z.dump.age [--yes]
#
# Sequenza (specifica fase 1 §4, disaster recovery):
#   1. verifica del checksum, se il file .sha256 è presente;
#   2. stop di api/worker/scheduler (nessuna scrittura durante il ripristino);
#   3. age -d e pg_restore --clean --if-exists nel container `postgres`;
#   4. `alembic upgrade head` one-shot (schema allineato alla revisione attesa);
#   5. riavvio dei servizi e attesa di /api/ready.
#
# Dopo il ripristino i SyncRun non terminali vanno riconciliati PRIMA di
# riabilitare lo scheduler: tenere SCHEDULER_ENABLED=false fino a fine
# riconciliazione. Lo script non lo fa al posto dell'operatore.
#
# Variabili (default fra parentesi):
#   COMPOSE_FILE              file compose (docker-compose.yml)
#   BACKUP_AGE_IDENTITY_FILE  chiave privata age (default: quella di age, ~/.config/age/keys.txt)
#   READY_TIMEOUT_SECONDS     attesa di /api/ready dopo il riavvio (120)

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.yml}"
BACKUP_AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:-}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-120}"
POSTGRES_DB="${POSTGRES_DB:-mdbup}"
POSTGRES_USER="${POSTGRES_USER:-mdbup}"

log() {
    printf '%s restore: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

die() {
    log "ERRORE: $*"
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "comando richiesto non trovato: $1"
}

compose() {
    docker compose -f "${COMPOSE_FILE}" "$@"
}

usage() {
    printf 'Uso: %s <archivio.dump.age> [--yes]\n' "${0##*/}" >&2
    exit 2
}

ARCHIVE_FILE=""
ASSUME_YES=0

for arg in "$@"; do
    case "${arg}" in
        --yes|-y) ASSUME_YES=1 ;;
        -h|--help) usage ;;
        -*) die "opzione sconosciuta: ${arg}" ;;
        *)
            [[ -z ${ARCHIVE_FILE} ]] || die "specificare un solo archivio"
            ARCHIVE_FILE="${arg}"
            ;;
    esac
done

[[ -n ${ARCHIVE_FILE} ]] || usage

main() {
    require_cmd docker
    require_cmd age

    [[ -f ${ARCHIVE_FILE} ]] || die "archivio non trovato: ${ARCHIVE_FILE}"
    [[ -f ${COMPOSE_FILE} ]] || die "file compose non trovato: ${COMPOSE_FILE}"

    if [[ -f ${ARCHIVE_FILE}.sha256 ]]; then
        log "verifica checksum"
        (cd -- "$(dirname -- "${ARCHIVE_FILE}")" && sha256sum --check --quiet "$(basename -- "${ARCHIVE_FILE}").sha256") \
            || die "checksum non valido: ${ARCHIVE_FILE}"
    else
        log "ATTENZIONE: ${ARCHIVE_FILE##*/}.sha256 assente, checksum non verificato"
    fi

    if (( ASSUME_YES == 0 )); then
        printf 'Il ripristino SOSTITUISCE i dati del database corrente. Continuare? [scrivi "restore"] ' >&2
        local answer=""
        read -r answer || true
        [[ ${answer} == "restore" ]] || die "ripristino annullato"
    fi

    local plain
    plain=$(mktemp "${TMPDIR:-/tmp}/mdbup-restore-XXXXXX.dump")
    # shellcheck disable=SC2064
    trap "rm -f -- '${plain}'" EXIT

    log "decifratura age"
    if [[ -n ${BACKUP_AGE_IDENTITY_FILE} ]]; then
        age --decrypt --identity "${BACKUP_AGE_IDENTITY_FILE}" --output "${plain}" "${ARCHIVE_FILE}"
    else
        age --decrypt --output "${plain}" "${ARCHIVE_FILE}"
    fi

    log "stop di api, worker e scheduler"
    compose stop api worker scheduler

    log "pg_restore --clean --if-exists"
    compose exec -T postgres pg_restore \
        --clean \
        --if-exists \
        --no-owner \
        --no-privileges \
        --dbname="${POSTGRES_DB}" \
        --username="${POSTGRES_USER}" < "${plain}"

    log "allineamento schema (alembic upgrade head)"
    compose run --rm migrate

    log "riavvio dei servizi applicativi"
    compose start api worker scheduler

    log "attesa di /api/ready (max ${READY_TIMEOUT_SECONDS}s)"
    local waited=0
    until compose exec -T api python -c \
        "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3).status == 200 else 1)" \
        >/dev/null 2>&1; do
        if (( waited >= READY_TIMEOUT_SECONDS )); then
            die "/api/ready non risponde: controllare i log di api e migrate"
        fi
        sleep 5
        waited=$((waited + 5))
    done

    log "ripristino completato"
    log "PROMEMORIA: riconciliare i SyncRun non terminali prima di riabilitare lo scheduler (SCHEDULER_ENABLED=true)"
}

main "$@"
