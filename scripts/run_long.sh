#!/usr/bin/env bash
# Run the long run L (experiments/L.json: S11 with the long-run budget) and save one agent per seed.
#
# Steps, one after another; the script stops at the first step that fails:
#   0. Checks before anything runs: the BC start of every seed exists, and none of the agent
#      names is taken under AGENTS_ROOT (so the agents can be saved after the ~5 h run).
#   1. Trial: L with all 4 seeds, 8,192 steps, to /tmp/quack-trial-l. It stops when the peak
#      memory of the whole run is above 85% of PPO_MEM_MAX, and saves one trial agent into a
#      temporary agents root, so the save step is checked before the long run.
#   2. L in full, to data/experiments.
#   3. Reproducibility check (reported, does not stop): per seed, the ppo.csv rows of L up to
#      S11's budget (962,560) are compared with S11's, wall_seconds left out. Same config and
#      seed, so on this machine they should be equal; a difference is worth a look, not an error.
#   4. One agent per seed from its final checkpoint: AGENTS_ROOT/AGENT_PREFIX-seed<k>
#      (seat agent:<AGENT_PREFIX>-seed<k>, playable in the web app).
#
# The whole script runs under systemd-inhibit (no suspend, idle sleep or lid-switch sleep),
# since a suspended laptop pauses the run.
#
# Usage: scripts/run_long.sh [--skip-trial] [--resume] [--skip-agents]
#
#   --skip-trial   skip step 1
#   --resume       passed through to scripts/run_experiment.py for the full run (see
#                  experiments/README.md, "Resume after an interruption")
#   --skip-agents  skip step 4 (save them later with scripts/save_run_agent.py)
#
# Environment: PPO_MEM_MAX (default 6G), AGENTS_ROOT (default data/agents), AGENT_PREFIX
# (default long-s11), LOG (default data/experiments/run_long.log).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${QUACK_INHIBITED:-}" ]; then
    export QUACK_INHIBITED=1
    exec systemd-inhibit --what=sleep:idle:handle-lid-switch --who=quack-rl \
        --why="long PPO run L" "$0" "$@"
fi

CONFIG=experiments/L.json
TRIAL_OUT=/tmp/quack-trial-l
OUT=data/experiments
TRIAL_STEPS=8192
SEEDS=(0 1 2 3)
PPO_MEM_MAX=${PPO_MEM_MAX:-6G}
AGENTS_ROOT=${AGENTS_ROOT:-data/agents}
AGENT_PREFIX=${AGENT_PREFIX:-long-s11}
LOG=${LOG:-data/experiments/run_long.log}

skip_trial=0
skip_agents=0
resume=()
for arg in "$@"; do
    case "$arg" in
        --skip-trial) skip_trial=1 ;;
        --skip-agents) skip_agents=1 ;;
        --resume) resume=(--resume) ;;
        -h|--help) sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

save_agent() {
    uv run --group rl python scripts/save_run_agent.py "$@"
}

# 0. Checks before anything runs
for k in "${SEEDS[@]}"; do
    if [ ! -f "$OUT/B2/seed$k/model.pt" ]; then
        log "$OUT/B2/seed$k/model.pt is missing: PPO seed $k cannot start; stopping"
        exit 1
    fi
    if [ "$skip_agents" -eq 0 ] && [ -e "$AGENTS_ROOT/$AGENT_PREFIX-seed$k/agent.json" ]; then
        log "the agent $AGENT_PREFIX-seed$k already exists in $AGENTS_ROOT; set AGENT_PREFIX" \
            "or AGENTS_ROOT, or pass --skip-agents; stopping"
        exit 1
    fi
done

# 1. Trial
if [ "$skip_trial" -eq 0 ]; then
    rm -rf "$TRIAL_OUT"
    run_one "L trial (seeds 0-3, $TRIAL_STEPS steps)" "$PPO_MEM_MAX" \
        --config "$CONFIG" --out "$TRIAL_OUT" --steps "$TRIAL_STEPS" --threads 1
    cap_bytes=$(numfmt --from=iec "$PPO_MEM_MAX")
    if [ -n "$LAST_SCOPE_PEAK" ] && [ "$LAST_SCOPE_PEAK" -gt $((cap_bytes * 85 / 100)) ]; then
        log "L trial: peak memory $((LAST_SCOPE_PEAK / 1024)) kB is above 85% of" \
            "PPO_MEM_MAX $PPO_MEM_MAX; raise PPO_MEM_MAX and run again"
        exit 1
    fi
    trial_agents=$(mktemp -d)
    save_agent "$TRIAL_OUT/L/seed0" --agent-name trial --agents-root "$trial_agents"
    rm -rf "$trial_agents"
    log "L trial: agent save checked"
else
    log "L trial: skipped (--skip-trial)"
fi

# 2. The full run
run_one "L" "$PPO_MEM_MAX" --config "$CONFIG" --out "$OUT" --threads 1 "${resume[@]}"

# 3. Reproducibility check against S11 (reported only)
uv run python - "$OUT" <<'EOF' | tee -a "$LOG"
import csv, sys
from pathlib import Path

out = Path(sys.argv[1])
limit = 962560
for k in range(4):
    def rows(exp):
        path = out / exp / f"seed{k}" / "ppo.csv"
        if not path.is_file():
            return None
        with path.open(newline="") as handle:
            return [
                {key: v for key, v in row.items() if key != "wall_seconds"}
                for row in csv.DictReader(handle)
                if int(row["steps"]) <= limit
            ]
    s11, long = rows("S11"), rows("L")
    if s11 is None or long is None:
        print(f"reproducibility seed {k}: ppo.csv missing, not compared")
        continue
    first = next((a["steps"] for a, b in zip(s11, long) if a != b), None)
    if first is None and len(s11) == len(long):
        print(f"reproducibility seed {k}: L equals S11 up to {limit} ({len(s11)} rows)")
    else:
        print(f"reproducibility seed {k}: L differs from S11 from step {first or 'end'}")
EOF

# 4. The agents
if [ "$skip_agents" -eq 0 ]; then
    for k in "${SEEDS[@]}"; do
        save_agent "$OUT/L/seed$k" --agent-name "$AGENT_PREFIX-seed$k" \
            --agents-root "$AGENTS_ROOT" | tee -a "$LOG"
    done
else
    log "agents: skipped (--skip-agents)"
fi
log "L: all done"
