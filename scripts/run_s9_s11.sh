#!/usr/bin/env bash
# Run screening 5, the BC reruns S9, S10, S11 (S3, S4, S5 with S7's target_kl 0.03, seeds 0-3).
#
# Steps, one after another; the script stops at the first run that fails:
#   1. BC seed 3 of B0, B1, B2 (PPO seed 3 of S9/S10/S11 starts from it). An arm whose
#      seed3/done.json already exists is skipped. One arm at a time: a BC process loads the
#      whole dataset (about 2.5 GB).
#   2. Trial: S9 with all 4 seeds, 8,192 steps, to /tmp/quack-trial-s9. It checks that the
#      8 processes (4 trainings, 4 evaluators) fit the memory cap: if the peak memory of the
#      whole run is above 85% of PPO_MEM_MAX, the script stops before the full runs.
#   3. S9, S10, S11 in full, to data/experiments.
#
# Usage: scripts/run_s9_s11.sh [--skip-bc] [--skip-trial] [--resume]
#
#   --skip-bc     skip step 1
#   --skip-trial  skip step 2
#   --resume      passed through to scripts/run_experiment.py for the trial and the full runs
#
# Environment: PPO_MEM_MAX (default 6G) and BC_MEM_MAX (default 8G) set the MemoryMax of the
# systemd scope around each run (the cap is for the whole run, all its processes together);
# LOG (default data/experiments/run_s9_s11.log).
#
# The log gets one line per run: name, start and end (UTC), exit code, wall time, peak RSS of
# the largest process (/usr/bin/time -v) and the peak memory of the whole run (memory.peak of
# its scope, read every 5 s).
set -euo pipefail

cd "$(dirname "$0")/.."

TRIAL_OUT=/tmp/quack-trial-s9
OUT=data/experiments
TRIAL_STEPS=8192
PPO_MEM_MAX=${PPO_MEM_MAX:-6G}
BC_MEM_MAX=${BC_MEM_MAX:-8G}
LOG=${LOG:-data/experiments/run_s9_s11.log}

skip_bc=0
skip_trial=0
resume=()
for arg in "$@"; do
    case "$arg" in
        --skip-bc) skip_bc=1 ;;
        --skip-trial) skip_trial=1 ;;
        --resume) resume=(--resume) ;;
        -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

mkdir -p "$(dirname "$LOG")"

log() {
    echo "$*" | tee -a "$LOG"
}

# poll_peak <unit> <file>: write memory.peak of the scope <unit> to <file> every 5 s while
# the scope exists.
poll_peak() {
    local unit=$1 out=$2 cg="" i
    for i in $(seq 1 120); do
        cg=$(systemctl --user show -p ControlGroup --value "$unit" 2>/dev/null || true)
        [ -n "$cg" ] && break
        sleep 0.5
    done
    [ -n "$cg" ] || return 0
    local f=/sys/fs/cgroup$cg/memory.peak
    while [ -r "$f" ]; do
        cat "$f" > "$out.tmp" 2>/dev/null && mv "$out.tmp" "$out"
        sleep 5
    done
}

LAST_SCOPE_PEAK=""

# run_one <name> <MemoryMax> <run_experiment.py arguments...>
run_one() {
    local name=$1 cap=$2
    shift 2
    local unit="quack-run-$$-$RANDOM.scope"
    local timefile peakfile start end code peak wall scope_peak poller
    timefile=$(mktemp)
    peakfile=$(mktemp)
    start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    log "$name: start $start, git $(git rev-parse --short HEAD), MemoryMax $cap, args: $*"
    poll_peak "$unit" "$peakfile" &
    poller=$!
    set +e
    systemd-run --user --scope --unit="$unit" -p MemoryMax="$cap" -p MemorySwapMax=0 \
        /usr/bin/time -v -o "$timefile" \
        uv run --group rl python scripts/run_experiment.py "$@"
    code=$?
    set -e
    end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    kill "$poller" 2>/dev/null || true
    wait "$poller" 2>/dev/null || true
    peak=$(sed -n 's/^[[:space:]]*Maximum resident set size (kbytes): //p' "$timefile")
    wall=$(sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss): //p' "$timefile")
    scope_peak=$(cat "$peakfile" 2>/dev/null || true)
    rm -f "$timefile" "$peakfile" "$peakfile.tmp"
    LAST_SCOPE_PEAK=$scope_peak
    local scope_text=unknown
    [ -n "$scope_peak" ] && scope_text="$((scope_peak / 1024)) kB"
    log "$name: end $end, exit code $code, wall ${wall:-unknown}," \
        "peak RSS (largest process) ${peak:-unknown} kB, peak memory (whole run) $scope_text"
    if [ "$code" -ne 0 ]; then
        log "$name failed (exit code $code); stopping"
        exit "$code"
    fi
}

# 1. BC seed 3
if [ "$skip_bc" -eq 0 ]; then
    for bc in B0 B1 B2; do
        if [ -f "$OUT/$bc/seed3/done.json" ] && [ -f "$OUT/$bc/seed3/model.pt" ]; then
            log "$bc seed 3: done.json and model.pt exist, skipped"
            continue
        fi
        run_one "$bc seed 3" "$BC_MEM_MAX" \
            --config "experiments/$bc.json" --out "$OUT" --seeds 3 --threads 1
    done
else
    log "BC seed 3: skipped (--skip-bc)"
fi

for bc in B0 B1 B2; do
    if [ ! -f "$OUT/$bc/seed3/model.pt" ]; then
        log "$OUT/$bc/seed3/model.pt is missing: PPO seed 3 cannot start; stopping"
        exit 1
    fi
done

# 2. Trial of S9 with all 4 seeds
if [ "$skip_trial" -eq 0 ]; then
    run_one "S9 trial (seeds 0-3, $TRIAL_STEPS steps)" "$PPO_MEM_MAX" \
        --config experiments/S9.json --out "$TRIAL_OUT" --steps "$TRIAL_STEPS" --threads 1 \
        "${resume[@]}"
    cap_bytes=$(numfmt --from=iec "$PPO_MEM_MAX")
    if [ -n "$LAST_SCOPE_PEAK" ] && [ "$LAST_SCOPE_PEAK" -gt $((cap_bytes * 85 / 100)) ]; then
        log "S9 trial: peak memory $((LAST_SCOPE_PEAK / 1024)) kB is above 85% of" \
            "PPO_MEM_MAX $PPO_MEM_MAX; raise PPO_MEM_MAX and run again with --skip-bc --skip-trial"
        exit 1
    fi
else
    log "S9 trial: skipped (--skip-trial)"
fi

# 3. The full runs
for id in S9 S10 S11; do
    run_one "$id" "$PPO_MEM_MAX" \
        --config "experiments/$id.json" --out "$OUT" --threads 1 "${resume[@]}"
done
log "S9, S10, S11: all done"
