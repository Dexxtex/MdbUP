#!/usr/bin/env bash
#
# MdbUP — backup logico di PostgreSQL, cifrato con age, con retention GFS.
#
# Cosa si salva: solo PostgreSQL. Redis non è un asset: i job persi vengono
# riportati a VERIFYING dai SyncRun non terminali (docs/phases/phase-01.md §4).
#
# Uso (host, stack già avviato):
#   deploy/scripts/backup.sh
#
# Prerequisiti sull'host: docker compose, age, sha256sum, GNU coreutils (date -d).
# Nessun client PostgreSQL è richiesto sull'host: pg_dump e pg_restore girano
# nel container `postgres`, quindi la versione del client coincide sempre con
# quella del server.
#
# Variabili (default fra parentesi):
#   COMPOSE_FILE                  file compose (docker-compose.yml)
#   BACKUP_DIR                    directory di destinazione (./backups)
#   BACKUP_STATUS_FILE            stato letto da api/worker (${BACKUP_DIR}/last_backup.json)
#   BACKUP_RETENTION_DAILY        backup giornalieri da tenere (7)
#   BACKUP_RETENTION_WEEKLY       backup settimanali da tenere (4)
#   BACKUP_RETENTION_MONTHLY      backup mensili da tenere (6)
#   BACKUP_RETENTION_DAYS         età massima in giorni, 0 = disabilitato (180)
#   BACKUP_AGE_RECIPIENT_FILE     file con la chiave pubblica age (secrets/backup_age_recipient)
#   POSTGRES_DB / POSTGRES_USER   database e ruolo da esportare (mdbup / mdbup)
#
# La chiave privata age non sta su questo host: senza di essa il backup non è
# ripristinabile. APP_ENCRYPTION_KEY è un asset separato: senza di essa il dump
# si ripristina ma le credenziali restano illeggibili.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-${BACKUP_DIR}/last_backup.json}"
BACKUP_RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-6}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-180}"
BACKUP_AGE_RECIPIENT_FILE="${BACKUP_AGE_RECIPIENT_FILE:-${REPO_ROOT}/secrets/backup_age_recipient}"
POSTGRES_DB="${POSTGRES_DB:-mdbup}"
POSTGRES_USER="${POSTGRES_USER:-mdbup}"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP_FILE="${BACKUP_DIR}/mdbup-${STAMP}.dump"
TOC_FILE="${BACKUP_DIR}/mdbup-${STAMP}.toc"
ARCHIVE_FILE="${DUMP_FILE}.age"

log() {
    printf '%s backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
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

# Un backup parziale non deve restare in BACKUP_DIR: sembrerebbe valido e
# verrebbe conteggiato dalla retention.
cleanup_on_error() {
    local rc=$?
    if (( rc != 0 )); then
        rm -f -- "${DUMP_FILE}" "${TOC_FILE}" "${ARCHIVE_FILE}" "${ARCHIVE_FILE}.sha256"
        write_status "FAILED" "backup fallito (exit ${rc})"
        log "backup fallito (exit ${rc}): artefatti parziali rimossi"
    fi
}

json_escape() {
    local value=${1//\\/\\\\}
    value=${value//\"/\\\"}
    printf '%s' "${value}"
}

# Stato leggibile da /api/metrics e /api/system/status. Scrittura atomica: i
# lettori non vedono mai un file a metà. Non è un backup: la retention non lo
# tocca perché pota solo i file `mdbup-*`.
write_status() {
    local status=$1
    local error=${2:-}
    local file="null" size=0 sha="null" tmp="${BACKUP_STATUS_FILE}.tmp"
    if [[ -f ${ARCHIVE_FILE} ]]; then
        file="\"$(json_escape "${ARCHIVE_FILE##*/}")\""
        size=$(stat -c %s -- "${ARCHIVE_FILE}")
    fi
    if [[ -f ${ARCHIVE_FILE}.sha256 ]]; then
        sha="\"$(cut -d' ' -f1 < "${ARCHIVE_FILE}.sha256")\""
    fi
    mkdir -p -- "$(dirname -- "${BACKUP_STATUS_FILE}")"
    printf '{"timestamp":"%s","file":%s,"size":%s,"sha256":%s,"status":"%s","error":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${file}" "${size}" "${sha}" "${status}" \
        "$([[ -n ${error} ]] && printf '"%s"' "$(json_escape "${error}")" || printf 'null')" \
        > "${tmp}"
    mv -f -- "${tmp}" "${BACKUP_STATUS_FILE}"
}

# Estrae lo stamp UTC (YYYYMMDDTHHMMSSZ) dal nome di un archivio di backup.
stamp_of() {
    local base=${1##*/}
    base=${base#mdbup-}
    printf '%s\n' "${base%%.dump.age}"
}

# Data ISO (YYYY-MM-DD) ricavata dallo stamp nel nome del file: indipendente
# da mtime e da come il file è stato copiato.
iso_day_of() {
    local stamp=$1
    printf '%s-%s-%s\n' "${stamp:0:4}" "${stamp:4:2}" "${stamp:6:2}"
}

iso_week_of() {
    local stamp=$1
    local iso="${stamp:0:4}-${stamp:4:2}-${stamp:6:2} ${stamp:9:2}:${stamp:11:2}:${stamp:13:2}"
    date -u -d "${iso}" +%G-W%V
}

iso_month_of() {
    local stamp=$1
    printf '%s-%s\n' "${stamp:0:4}" "${stamp:4:2}"
}

# Retention GFS: un backup per giorno/settimana/mese, dal più recente.
# Regola di sicurezza: se il backup più recente non è di oggi, la potatura è
# saltata — un backup fallito non deve cancellare la storia disponibile.
prune_backups() {
    # Ordine dal più recente al più vecchio dedotto dal nome (mdbup-<STAMP>.dump.age):
    # l'mtime cambia con copie e ripristini, lo stamp nel nome no.
    local -a archives=()
    mapfile -t archives < <(ls -1 "${BACKUP_DIR}"/mdbup-*.dump.age 2>/dev/null | sort -r || true)
    if [[ ${#archives[@]} -eq 0 ]]; then
        log "retention: nessun archivio presente"
        return 0
    fi

    local today newest_day
    today=$(date -u +%Y-%m-%d)
    newest_day=$(iso_day_of "$(stamp_of "${archives[0]}")")
    if [[ ${newest_day} != "${today}" ]]; then
        log "retention: nessun backup di oggi (più recente: ${newest_day}), potatura saltata"
        return 0
    fi

    local -A keep=()
    local -A seen_day=() seen_week=() seen_month=()
    local daily=0 weekly=0 monthly=0
    local file stamp day week month

    for file in "${archives[@]}"; do
        stamp=$(stamp_of "${file}")
        day=$(iso_day_of "${stamp}")
        week=$(iso_week_of "${stamp}")
        month=$(iso_month_of "${stamp}")

        if [[ -z ${seen_day[${day}]:-} ]] && (( daily < BACKUP_RETENTION_DAILY )); then
            seen_day[${day}]=1
            keep[${file}]=1
            daily=$((daily + 1))
        fi
        if [[ -z ${seen_week[${week}]:-} ]] && (( weekly < BACKUP_RETENTION_WEEKLY )); then
            seen_week[${week}]=1
            keep[${file}]=1
            weekly=$((weekly + 1))
        fi
        if [[ -z ${seen_month[${month}]:-} ]] && (( monthly < BACKUP_RETENTION_MONTHLY )); then
            seen_month[${month}]=1
            keep[${file}]=1
            monthly=$((monthly + 1))
        fi
    done

    # Hard age cap: even a monthly GFS slot is removed after N days. The
    # newest archive is never deleted, even if the clock is wrong.
    if (( BACKUP_RETENTION_DAYS > 0 )); then
        local cutoff_epoch file_epoch iso
        cutoff_epoch=$(date -u -d "-${BACKUP_RETENTION_DAYS} days" +%s)
        for file in "${archives[@]}"; do
            [[ ${file} == "${archives[0]}" ]] && continue
            stamp=$(stamp_of "${file}")
            iso="${stamp:0:4}-${stamp:4:2}-${stamp:6:2} ${stamp:9:2}:${stamp:11:2}:${stamp:13:2}"
            file_epoch=$(date -u -d "${iso}" +%s)
            if (( file_epoch < cutoff_epoch )); then
                rm -f -- "${file}" "${file}.sha256" "${file%.dump.age}.toc"
                log "retention: rimosso per età (${BACKUP_RETENTION_DAYS}g) ${file##*/}"
            fi
        done
    fi

    for file in "${archives[@]}"; do
        if [[ -z ${keep[${file}]:-} ]]; then
            rm -f -- "${file}" "${file}.sha256" "${file%.dump.age}.toc"
            log "retention: rimosso ${file##*/}"
        fi
    done
}

main() {
    require_cmd docker
    require_cmd age
    require_cmd sha256sum

    [[ -f ${BACKUP_AGE_RECIPIENT_FILE} ]] \
        || die "chiave pubblica age non trovata: ${BACKUP_AGE_RECIPIENT_FILE}"
    [[ -f ${COMPOSE_FILE} ]] || die "file compose non trovato: ${COMPOSE_FILE}"

    mkdir -p "${BACKUP_DIR}"
    trap cleanup_on_error EXIT

    log "pg_dump di ${POSTGRES_DB} (formato custom, compresso)"
    compose exec -T postgres pg_dump \
        --format=custom \
        --compress=9 \
        --no-owner \
        --no-privileges \
        --username="${POSTGRES_USER}" \
        --dbname="${POSTGRES_DB}" > "${DUMP_FILE}"

    [[ -s ${DUMP_FILE} ]] || die "pg_dump ha prodotto un archivio vuoto"

    # Indice del dump: permette di ispezionare l'archivio senza ripristinarlo.
    compose exec -T postgres pg_restore --list < "${DUMP_FILE}" > "${TOC_FILE}"

    log "cifratura age"
    age --encrypt \
        --recipients-file "${BACKUP_AGE_RECIPIENT_FILE}" \
        --output "${ARCHIVE_FILE}" \
        "${DUMP_FILE}"

    # Checksum con nome relativo: gli archivi restano verificabili anche dopo
    # essere stati copiati su un altro host (vedi restore.sh).
    (cd -- "${BACKUP_DIR}" && sha256sum "${ARCHIVE_FILE##*/}") > "${ARCHIVE_FILE}.sha256"

    # Il dump in chiaro non resta mai su disco: esiste solo per la cifratura.
    rm -f -- "${DUMP_FILE}"

    write_status "OK"
    log "creato ${ARCHIVE_FILE##*/} ($(du -h "${ARCHIVE_FILE}" | cut -f1))"
    prune_backups
}

main "$@"
