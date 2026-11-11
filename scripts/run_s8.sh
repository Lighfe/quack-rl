#!/usr/bin/env bash
# Run screening arm S8 (experiments/S8.json): first an 8,192-step trial run of seed 0 to
# /tmp/quack-trial-s8, then the full run (seeds 0, 1, 2) to data/experiments.
#
# Usage: scripts/run_s8.sh [--skip-trial] [--resume]
#
#   --skip-trial  skip the trial run
#   --resume      passed through to scripts/run_experiment.py (for both runs)
#
# Each run goes in the memory cap wrapper of experiments/README.md ("Run an experiment"). The
# log file (default data/experiments/run_s8.log, set LOG=<file> to change it) gets one line per
# run: name, start and end (UTC), exit code and peak RSS ("Maximum resident set size" of
# /usr/bin/time -v). The script stops at the first run that fails.
#
# A trial folder left from an earlier trial stops the trial run (run_experiment.py refuses a
# seed folder with a config.json without --resume): delete /tmp/quack-trial-s8 first, or pass
# --skip-trial.
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG=experiments/S8.json
TRIAL_OUT=/tmp/quack-trial-s8
OUT=data/experiments
TRIAL_STEPS=8192
LOG=${LOG:-data/experiments/run_s8.log}

skip_trial=0
resume=()
for arg in "$@"; do
    case "$arg" in
        --skip-trial) skip_trial=1 ;;
        --resume) resume=(--resume) ;;
        -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

mkdir -p "$(dirname "$LOG")"

log() {
    echo "$*" | tee -a "$LOG"
}

# run_one <name> <run_experiment.py arguments...>
run_one() {
    local name=$1
    shift
    local timefile
    timefile=$(mktemp)
    local start end code peak
    start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    log "$name: start $start, git $(git rev-parse --short HEAD), args: $*"
    set +e
    systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
        /usr/bin/time -v -o "$timefile" \
        uv run --group rl python scripts/run_experiment.py "$@"
    code=$?
    set -e
    end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    peak=$(sed -n 's/^[[:space:]]*Maximum resident set size (kbytes): //p' "$timefile")
    wall=$(sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss): //p' "$timefile")
    rm -f "$timefile"
    log "$name: end $end, exit code $code, wall ${wall:-unknown}, peak RSS ${peak:-unknown} kB"
    if [ "$code" -ne 0 ]; then
        log "$name failed (exit code $code); stopping"
        exit "$code"
    fi
}

if [ "$skip_trial" -eq 0 ]; then
    run_one "S8 trial (seed 0, $TRIAL_STEPS steps)" \
        --config "$CONFIG" --out "$TRIAL_OUT" --seeds 0 --steps "$TRIAL_STEPS" --threads 1 \
        "${resume[@]}"
else
    log "S8 trial: skipped (--skip-trial)"
fi

run_one "S8" --config "$CONFIG" --out "$OUT" --threads 1 "${resume[@]}"
