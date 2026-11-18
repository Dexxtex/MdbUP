#!/usr/bin/env bash
#
# MdbUP — verifica dell'ultimo backup cifrato, eseguita sull'host.
#
# Controlli, in ordine:
#   1. esiste almeno un archivio `mdbup-*.dump.age` in BACKUP_DIR;
#   2. l'archivio non è vuoto;
#   3. l'hash sha256 coincide con il file `.sha256` scritto da backup.sh;
#   4. l'archivio ha l'header age (`age-encryption.org/v1`);
#   5. se BACKUP_AGE_IDENTITY_FILE è presente e il binario `age` è installato,
#      l'archivio viene decifrato in una directory temporanea e si verifica il
#      magic `PGDMP` del dump PostgreSQL.
#
# L'esito aggiorna BACKUP_STATUS_FILE (default ${BACKUP_DIR}/last_backup.json),
# letto da /api/metrics e /api/system/status. La chiave privata age non viene
# mai stampata: i log riportano solo nome file, dimensione e stato.
#
# Uso (host):
#   scripts/backup-verify.sh
#
# Variabili (default fra parentesi):
#   BACKUP_DIR                    directory dei backup (./backups)
#   BACKUP_STATUS_FILE            file di stato (${BACKUP_DIR}/last_backup.json)
#   BACKUP_AGE_IDENTITY_FILE      chiave privata age (nessuna: verifica senza decifratura)
#
# Exit code: 0 se lo stato finale è OK, 1 altrimenti.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)

BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-${BACKUP_DIR}/last_backup.json}"
BACKUP_AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:-}"

STATUS="MISSING"
ERROR=""
ARCHIVE=""
ARCHIVE_SIZE=0
ARCHIVE_SHA=""
DECRYPTED="false"
AGE_AVAILABLE="false"

log() {
    printf '%s backup-verify: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

json_escape() {
    local value=${1//\\/\\\\}
    value=${value//\"/\\\"}
    printf '%s' "${value}"
}

# Scrittura atomica: un lettore (api/worker) non vede mai un file a metà.
write_status() {
    local tmp="${BACKUP_STATUS_FILE}.tmp"
    mkdir -p -- "$(dirname -- "${BACKUP_STATUS_FILE}")"
    printf '{"timestamp":"%s","file":%s,"size":%s,"sha256":%s,"status":"%s","error":%s,"decrypted":%s,"age_available":%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$([[ -n ${ARCHIVE} ]] && printf '"%s"' "$(json_escape "${ARCHIVE}")" || printf 'null')" \
        "${ARCHIVE_SIZE}" \
        "$([[ -n ${ARCHIVE_SHA} ]] && printf '"%s"' "${ARCHIVE_SHA}" || printf 'null')" \
        "${STATUS}" \
        "$([[ -n ${ERROR} ]] && printf '"%s"' "$(json_escape "${ERROR}")" || printf 'null')" \
        "${DECRYPTED}" \
        "${AGE_AVAILABLE}" > "${tmp}"
    mv -f -- "${tmp}" "${BACKUP_STATUS_FILE}"
}

fail() {
    STATUS=$1
    ERROR=$2
    log "ERRORE: ${ERROR}"
    write_status
    exit 1
}

verify() {
    local -a archives=()
    mapfile -t archives < <(ls -1 "${BACKUP_DIR}"/mdbup-*.dump.age 2>/dev/null | sort -r || true)
    if [[ ${#archives[@]} -eq 0 ]]; then
        fail "MISSING" "nessun archivio mdbup-*.dump.age in ${BACKUP_DIR}"
    fi
    ARCHIVE=${archives[0]##*/}
    local path=${archives[0]}

    ARCHIVE_SIZE=$(stat -c %s -- "${path}")
    if (( ARCHIVE_SIZE == 0 )); then
        fail "EMPTY" "archivio vuoto: ${ARCHIVE}"
    fi

    ARCHIVE_SHA=$(sha256sum -- "${path}" | cut -d' ' -f1)
    local checksum_file="${path}.sha256"
    if [[ ! -f ${checksum_file} ]]; then
        fail "CHECKSUM_MISSING" "file ${ARCHIVE}.sha256 assente"
    fi
    local expected
    expected=$(cut -d' ' -f1 < "${checksum_file}" | tr '[:upper:]' '[:lower:]')
    if [[ ${expected} != "${ARCHIVE_SHA}" ]]; then
        fail "CHECKSUM_MISMATCH" "sha256 di ${ARCHIVE} diverso da ${ARCHIVE}.sha256"
    fi

    local header
    header=$(head -c 21 -- "${path}")
    if [[ ${header} != "age-encryption.org/v1" ]]; then
        fail "INVALID_HEADER" "header age assente o non valido in ${ARCHIVE}"
    fi

    if command -v age >/dev/null 2>&1; then
        AGE_AVAILABLE="true"
    fi
    if [[ -n ${BACKUP_AGE_IDENTITY_FILE} && ${AGE_AVAILABLE} == "true" ]]; then
        if [[ ! -f ${BACKUP_AGE_IDENTITY_FILE} ]]; then
            fail "DECRYPT_FAILED" "chiave privata age non trovata: ${BACKUP_AGE_IDENTITY_FILE}"
        fi
        local tmpdir
        tmpdir=$(mktemp -d)
        # shellcheck disable=SC2064
        trap "rm -rf -- '${tmpdir}'" EXIT
        if ! age --decrypt --identity "${BACKUP_AGE_IDENTITY_FILE}" \
            --output "${tmpdir}/dump" -- "${path}" 2>/dev/null; then
            fail "DECRYPT_FAILED" "decifratura age non riuscita per ${ARCHIVE}"
        fi
        local magic
        magic=$(head -c 5 -- "${tmpdir}/dump")
        if [[ ${magic} != "PGDMP" ]]; then
            fail "PGDMP_INVALID" "il dump decifrato non ha il magic PGDMP"
        fi
        DECRYPTED="true"
    fi

    STATUS="OK"
    ERROR=""
    log "verificato ${ARCHIVE} (${ARCHIVE_SIZE} byte, sha256 ${ARCHIVE_SHA:0:12}…)"
}

verify
write_status
[[ ${STATUS} == "OK" ]] || exit 1
