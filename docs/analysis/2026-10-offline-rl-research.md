# Offline RL: dataset format and method, research

Issue #88. Checked on 2026-10-16 (all "checked" dates below are this day). Question: which dataset format and which offline method do #89 (dataset builder) and #90 (training and tournament) use, for a discrete-action policy with a legal-action mask? Every library claim has a link or names the local command that shows it.

## Project facts that matter

- `uv.lock` (checked in this repo): `requires-python = ">=3.12"`, Python of the environment 3.12.3 (`uv run python -c "import sys; print(sys.version)"`), `torch` 2.14.1, `stable-baselines3` 2.9.0, `sb3-contrib` 2.9.0, `gymnasium` 1.4.0, `numpy` 2.5.4, `pyarrow` 26.0.0 (`grep -A1 '^name = "torch"$' uv.lock` and the same for the others). `torch`, `stable-baselines3` and `sb3-contrib` are in the `train` group of `pyproject.toml`; `pyarrow` is a main dependency.
- The agent's view (`QuackEnv`, `src/quack_rl/rl/single_env.py`): a flat `float32` vector of 848 values and 15 discrete actions, and `action_masks()` returns an `int8` vector of 15. The episodes have different lengths (31 to 60 decisions of the learner in the toy runs below). At the terminal step the mask is all zero, so a terminal observation is never a training row.
- The project already writes Parquet with pyarrow (`seats.parquet` of a tournament, `src/quack_rl/tournament.py`). The game records themselves are JSON lines (`src/quack_rl/record/`).

## Minari: release, date, maintenance

| fact | value | source | checked |
|---|---|---|---|
| newest release | 0.5.4, uploaded 2026-09-29 | [PyPI minari](https://pypi.org/project/minari/0.5.4/), JSON: https://pypi.org/pypi/minari/json | 2026-10-16 |
| release before it | 0.5.3, 2025-04-17 (17 months gap) | same JSON, `releases` | 2026-10-16 |
| maintained? | yes: Farama Foundation project, not archived, last commit 2026-10-14 ("Add Python 3.14 support and CI coverage (#364)"), three commits between 2026-09-30 and 2026-10-14 | [repo](https://github.com/Farama-Foundation/Minari), [commits](https://github.com/Farama-Foundation/Minari/commits/main), `https://api.github.com/repos/Farama-Foundation/Minari` (`archived: false`, `pushed_at: 2026-10-14`) | 2026-10-16 |
| requires | Python >=3.11, `numpy>=2.0`, `gymnasium>=0.28.1`, `typer`, `typing_extensions`, `packaging`; the storage backends are extras (`hdf5` = `h5py>=3.8`, `arrow` = `pyarrow`) | PyPI JSON `requires_dist` | 2026-10-16 |

Verdict: Minari is current and maintained, but its releases are rare (one in 17 months) while the repository is active.

## Dataset formats compared

Options: (A) plain Parquet written with pyarrow, (B) Minari with the `arrow` storage, (C) Minari with the `hdf5` storage (the default in the docs), (D) the dataset of d3rlpy (`MDPDataset`, HDF5 file, see below). Numbers of A, B and C are from the toy run below (63,077 decisions of 1,500 real games, observation 848, mask 15), on the engineer's laptop (Intel i7-8650U, CPU only); one run each, so read them as an order of magnitude.

| topic | A: Parquet (pyarrow) | B: Minari `arrow` | C: Minari `hdf5` | D: d3rlpy `MDPDataset` |
|---|---|---|---|---|
| discrete actions | yes, an int column `action` | yes, `actions` int64 per episode (checked: actions of the toy dataset load equal to the Parquet ones) | same as B | yes, `DiscreteBC` and the other discrete algorithms take integer actions ([d3rlpy](https://github.com/takuseno/d3rlpy)) |
| action mask | extra column `action_mask`, `list<int8>` of 15, same row as the observation (shown below) | as part of a `Dict` observation space `{observation, action_mask}`; works (toy run: mask loads back equal) | same as B | no field for it; the library has no legal-action mask (`grep -rniE "action_mask\|legal\|masked" d3rlpy-2.8.1/d3rlpy` finds only the BCQ code comment and transformer attention masks, which are not legal-action masks) |
| episodes of different length | yes, column `episode` and `step`, one row per decision | yes, native: one episode per entry, 29 to 60 steps in the toy run | same as B | yes, episodes are cut by terminal flags |
| load speed in Python | 0.71 s for the 63,077 rows to NumPy arrays (includes the list-to-array stack of the two list columns) | 0.64 s to iterate all episodes and concatenate | 2.23 s, same work | not measured: not chosen (see the next section) |
| write speed | 5.2 s | 87.9 s (one folder per episode, 1,500 folders) | 2.7 s | not measured |
| size on disk | 4.6 MB | 223 MB | 255 MB | not measured |
| effort to write it from the existing game records | low: pyarrow is already a main dependency and `seats.parquet` is written the same way; one function that walks the games and appends rows | medium: needs the `EpisodeBuffer` objects (a plain dict fails, see below), a `Dict` observation space on a wrapper env, an extra dependency and its undeclared `pillow` import | medium, same as B | medium: needs conversion to `MDPDataset` and an extra dependency that downgrades `gymnasium` |

Findings from the run of the Minari option, with the code that shows them:

- `create_dataset_from_buffers` of 0.5.4 wants `EpisodeBuffer` objects. A list of dicts, as older examples show, fails with `AttributeError: 'dict' object has no attribute 'id'` (`minari/dataset/_storages/arrow_storage.py` and `hdf5_storage.py`, `update_episodes`; [source](https://github.com/Farama-Foundation/Minari/blob/main/minari/dataset/_storages/arrow_storage.py)).
- Both storages import `PIL` (`from PIL import Image`, line 11 of `arrow_storage.py` and `hdf5_storage.py` in the installed 0.5.4), but `pillow` is not in `requires_dist` of `minari` or of the extras `hdf5` and `arrow` (PyPI JSON). Without `--with pillow` the write stops with `ModuleNotFoundError: No module named 'PIL'`. So a Minari dependency would be `minari`, `pillow` and one of `h5py` / `pyarrow`.
- Minari adds nothing the project needs that Parquet does not give: no train/test split, no environment recovery for evaluation (the project has its own evaluation, `src/quack_rl/rl/evaluate.py`), and the dataset hub is of no use for a private game.

## Offline RL options compared

| topic | 1: behaviour cloning (BC), plain PyTorch | 2: d3rlpy 2.8.1 (`DiscreteBC`, `DiscreteCQL`, `DiscreteBCQ`) | 3: CORL-style code | 4: SB3 / sb3-contrib `MaskablePPO` |
|---|---|---|---|---|
| discrete actions | yes (cross-entropy over 15 logits) | yes | CORL covers continuous-control D4RL tasks; no discrete-action algorithm ([CORL](https://github.com/tinkoff-ai/CORL)) | yes |
| action masks | yes, set the logits of illegal actions to a large negative number before the softmax; shown to work below | no mask support (grep above): a trained Q-function or policy can choose an illegal action; the mask would have to be applied by wrapping the policy at play time, and training would still spend probability on illegal actions | not applicable | yes for online training (`MaskablePPO` is used in `src/quack_rl/rl/train.py`), but it has no offline dataset training; its policy could take BC weights as a start (a later step, not needed now) |
| install size | nothing new: `torch` is in the `train` group already (the locked Linux wheel of torch 2.14.1 is 555 MB, [PyPI](https://pypi.org/pypi/torch/2.14.1/json)); d3rlpy itself is a 0.2 MB wheel | `uv add --group train d3rlpy` in a copy of this project: 104 packages in the lock became 118 (14 more: `gym`, `h5py`, `scikit-learn`, `structlog`, ...) | not a package: files in a repo | already installed |
| compatibility with Python 3.12 and torch 2.14.1 of `uv.lock` | yes, it is the locked torch | d3rlpy 2.8.1 declares `torch>=2.5.0` and `gymnasium==1.0.0`, Python >=3.9 ([setup.py](https://github.com/takuseno/d3rlpy/blob/master/setup.py), PyPI JSON). In the copy of this project `uv add --group train "d3rlpy==2.8.1"` downgraded `gymnasium` from 1.4.0 to 1.0.0; plain `uv add --group train d3rlpy` picked 2.8.0 and kept 1.4.0. Latest release 2025-03-02, last commit 2025-09-10 ([commits](https://github.com/takuseno/d3rlpy)) | the repository is archived (read-only), last commit 2023-08-03 (`https://api.github.com/repos/tinkoff-ai/CORL`: `archived: true`) | yes, locked |

## Decision

Dataset format: Parquet, written with pyarrow (already a main dependency). Offline method: behaviour cloning in plain PyTorch with a masked cross-entropy loss, as the first offline baseline for #89 and #90. No new dependency: `pyproject.toml` and `uv.lock` stay as they are.

Reason in plain words: the dataset is simple (a vector of 848 numbers, 15 actions, a mask of 15, episodes of 29 to 60 decisions), and Parquet holds it in one small file (4.6 MB for 63,077 decisions, against 223 to 255 MB in Minari) that the project can already write and read. Minari works but costs a dependency with an undeclared `pillow` import, a wrapper environment for the `Dict` observation, 17x slower writes (arrow storage) and a 50x larger folder, and gives nothing the project needs in return. For the method, the only library that offers ready offline algorithms for discrete actions (d3rlpy) has no legal-action mask and pins `gymnasium` to 1.0.0 in its newest release; the algorithm that matters first, BC, is a few lines of PyTorch that honour the mask. If a later issue wants return-aware offline learning (for example weighting the loss by the game result or keeping only the games of the winner), it is a change of the loss in the same code, still without a dependency. Revisit d3rlpy only if a later stage shows that plain BC is not enough and masks can be handled outside the library.

Not decided here: which games fill the dataset (bot games, tournament games) and how many; that is #89.

### How the legal-action mask is stored and used

- Stored: one row per decision of the learner. Columns `episode` (int32), `step` (int32), `obs` (`list<float32>`, 848), `action_mask` (`list<int8>`, 15, the mask of the state the action was taken in), `action` (int16), and later the reward or result columns #89 needs. The mask is its own column, not part of `obs`, so the network input stays the 848 values the online agent sees. The terminal observation (all-zero mask) is not stored.
- Used in training: `logits = net(obs).masked_fill(~mask, -1e9)`, then `cross_entropy(logits, action)`. The chosen action is always legal in the data, so the loss is finite. At play time the same masked `argmax` (or sample) is used, so an illegal action cannot be chosen. A check in the toy run: the stored action was legal in every row, and the greedy action of the trained network was legal in every row.

## Checks by a small run

Both runs use real `QuackEnv` games with a random legal player (toy data, no claim about play strength).

### The decision: Parquet and masked BC, existing environment, no new dependency

Command (from the repo root, nothing was added to `pyproject.toml` or `uv.lock`): `uv run --group train python toy_parquet_bc.py` (the script is below). Output:

```
rows 1240 obs (1240, 848) mask (1240, 15) load s 0.054
action legal in every row: True
episodes of different length: [np.int64(31), np.int64(32), np.int64(34), np.int64(35), np.int64(36)] ...
iter 0 masked BC loss 0.7904
iter 1 masked BC loss 0.6583
iter 2 masked BC loss 0.6094
iter 3 masked BC loss 0.5712
iter 4 masked BC loss 0.5825
greedy action legal in every row: True
```

(The loss is not monotone: the toy has random actions as labels, so there is little to learn; the run only shows that the data round trip and the masked loss work.)

<details><summary>toy_parquet_bc.py</summary>

```python
"""Toy check of the decision: decisions of real games -> one Parquet file -> masked BC step."""
import os, tempfile, time
import numpy as np, pyarrow as pa, pyarrow.parquet as pq, torch
from quack_rl.rl.single_env import QuackEnv

env, rng, rows = QuackEnv(seat="p1"), np.random.default_rng(0), []
for g in range(30):
    obs, _ = env.reset(seed=g)
    mask = env.action_masks()
    for step in range(10_000):
        a = int(rng.choice(np.flatnonzero(mask)))          # random legal action as toy "expert"
        rows.append((g, step, obs, mask.copy(), a))        # state, mask of that state, action taken
        obs, r, te, tr, _ = env.step(a)
        mask = env.action_masks()
        if te or tr:
            break                                          # terminal obs has an all-zero mask: not stored
table = pa.table({
    "episode": pa.array([r[0] for r in rows], pa.int32()),
    "step": pa.array([r[1] for r in rows], pa.int32()),
    "obs": pa.array([r[2].tolist() for r in rows], pa.list_(pa.float32())),
    "action_mask": pa.array([r[3].tolist() for r in rows], pa.list_(pa.int8())),
    "action": pa.array([r[4] for r in rows], pa.int16()),
})
path = os.path.join(tempfile.mkdtemp(), "toy.parquet")
pq.write_table(table, path)
t0 = time.perf_counter()
tb = pq.read_table(path)
X = np.stack(tb["obs"].to_numpy(zero_copy_only=False)).astype(np.float32)
M = np.stack(tb["action_mask"].to_numpy(zero_copy_only=False)).astype(bool)
A = tb["action"].to_numpy().astype(np.int64)
print("rows", len(A), "obs", X.shape, "mask", M.shape, "load s", round(time.perf_counter() - t0, 3))
print("action legal in every row:", bool(M[np.arange(len(A)), A].all()))
print("episodes of different length:", sorted(set(np.bincount(tb["episode"].to_numpy()))) [:5], "...")
net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], 64), torch.nn.ReLU(), torch.nn.Linear(64, M.shape[1]))
opt = torch.optim.Adam(net.parameters(), 1e-3)
xt, mt, at = torch.from_numpy(X), torch.from_numpy(M), torch.from_numpy(A)
for it in range(5):
    logits = net(xt).masked_fill(~mt, -1e9)                # illegal actions get ~zero probability
    loss = torch.nn.functional.cross_entropy(logits, at)
    opt.zero_grad(); loss.backward(); opt.step()
    print("iter", it, "masked BC loss", round(loss.item(), 4))
pred = net(xt).masked_fill(~mt, -1e9).argmax(1)
print("greedy action legal in every row:", bool(mt[torch.arange(len(pred)), pred].all()))
```

</details>

### The comparison run: Minari (both storages) against Parquet

Command: `FMT=arrow uv run --group train --with "minari[hdf5,arrow]" --with pillow python -W ignore toy.py 1500`, and the same with `FMT=hdf5`. `uv run --with` installs Minari for the run only, so the project files are unchanged. Output (the `ls` of the 1,500 episode folders is left out):

```
episodes 1500 decisions 63077 min/max len 29 60 obs_dim 848 n_actions 15
parquet write s 5.216 bytes 4631741
parquet load s 0.7194 (63077, 848) (63077, 15) (63077,) chosen action legal in all rows: True
minari write s 87.888 total_episodes 1500 total_steps 63077        # FMT=arrow
minari bytes 223339366
minari load s 0.6426 (63077, 848) (63077, 15) (63077,) equal to parquet: True
---
parquet write s 5.222 bytes 4631741                                # FMT=hdf5
parquet load s 0.707 (63077, 848) (63077, 15) (63077,) chosen action legal in all rows: True
minari write s 2.667 total_episodes 1500 total_steps 63077
minari bytes 254808870
minari load s 2.233 (63077, 848) (63077, 15) (63077,) equal to parquet: True
```

With 30 games (1,240 decisions) the same script printed, for `FMT=hdf5`: Parquet 85 KB, Minari 5.0 MB, both loads equal. The loaded Minari arrays are equal to the Parquet arrays (observation, mask and action), so both formats keep the mask without loss.

<details><summary>toy.py</summary>

```python
"""Toy check: real QuackEnv episodes -> Parquet and Minari; load both; BC step with masked CE."""
import sys, time, tempfile, os
import numpy as np, gymnasium as gym
from gymnasium import spaces
import pyarrow as pa, pyarrow.parquet as pq
from quack_rl.rl.single_env import QuackEnv

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
env = QuackEnv(seat="p1")
rng = np.random.default_rng(0)
eps = []
for g in range(N):
    obs, info = env.reset(seed=g)
    mask = env.action_masks()
    ep = dict(obs=[obs], mask=[mask], act=[], rew=[], term=[], trunc=[])
    while True:
        a = int(rng.choice(np.flatnonzero(mask)))
        obs, r, te, tr, info = env.step(a)
        ep["act"].append(a); ep["rew"].append(r); ep["term"].append(te); ep["trunc"].append(tr)
        mask = env.action_masks()
        ep["obs"].append(obs); ep["mask"].append(mask)
        if te or tr: break
    eps.append(ep)
lens = [len(e["act"]) for e in eps]
print("episodes", N, "decisions", sum(lens), "min/max len", min(lens), max(lens),
      "obs_dim", eps[0]["obs"][0].shape[0], "n_actions", env.action_space.n)

d = tempfile.mkdtemp()
# --- Parquet: one row per decision, mask as list<int8>, last obs of an episode dropped
rows = dict(episode=[], step=[], obs=[], mask=[], action=[], reward=[], terminated=[])
for i, e in enumerate(eps):
    for t in range(len(e["act"])):
        rows["episode"].append(i); rows["step"].append(t); rows["obs"].append(e["obs"][t])
        rows["mask"].append(e["mask"][t]); rows["action"].append(e["act"][t])
        rows["reward"].append(e["rew"][t]); rows["terminated"].append(e["term"][t])
t0 = time.perf_counter()
tab = pa.table(dict(
    episode=pa.array(rows["episode"], pa.int32()), step=pa.array(rows["step"], pa.int32()),
    obs=pa.array([o.tolist() for o in rows["obs"]], pa.list_(pa.float32())),
    mask=pa.array([m.tolist() for m in rows["mask"]], pa.list_(pa.int8())),
    action=pa.array(rows["action"], pa.int16()), reward=pa.array(rows["reward"], pa.float32()),
    terminated=pa.array(rows["terminated"], pa.bool_())))
pq.write_table(tab, f"{d}/toy.parquet"); print("parquet write s", round(time.perf_counter() - t0, 3),
      "bytes", os.path.getsize(f"{d}/toy.parquet"))
t0 = time.perf_counter()
tb = pq.read_table(f"{d}/toy.parquet")
od = len(rows["obs"][0])
X = np.stack(tb["obs"].to_numpy(zero_copy_only=False)).astype(np.float32)
M = np.stack(tb["mask"].to_numpy(zero_copy_only=False)).astype(np.int8)
A = tb["action"].to_numpy()
print("parquet load s", round(time.perf_counter() - t0, 4), X.shape, M.shape, A.shape,
      "chosen action legal in all rows:", bool(M[np.arange(len(A)), A].all()))

# --- Minari
import minari
from minari.data_collector.episode_buffer import EpisodeBuffer
class MaskObs(gym.Wrapper):
    def __init__(self, env):
        super().__init__(env)
        self.observation_space = spaces.Dict(
            observation=env.observation_space, action_mask=spaces.MultiBinary(int(env.action_space.n)))
spec_env = MaskObs(env)
buffers = []
for e in eps:
    buffers.append(EpisodeBuffer(
        observations=dict(observation=np.stack(e["obs"]), action_mask=np.stack(e["mask"]).astype(np.int8)),
        actions=np.asarray(e["act"], dtype=np.int64), rewards=np.asarray(e["rew"], np.float32),
        terminations=np.asarray(e["term"]), truncations=np.asarray(e["trunc"])))
os.environ["MINARI_DATASETS_PATH"] = f"{d}/minari"
t0 = time.perf_counter()
ds = minari.create_dataset_from_buffers("quack/toy-v0", buffer=buffers, env=spec_env,
                                         algorithm_name="random", code_permalink="local", data_format=os.environ.get("FMT","hdf5"))
print("minari write s", round(time.perf_counter() - t0, 3), "total_episodes", ds.total_episodes,
      "total_steps", ds.total_steps)
size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(f"{d}/minari") for f in fs)
print("minari bytes", size, sorted(os.listdir(os.path.join(d, "minari", "quack", "toy-v0", "data"))))
t0 = time.perf_counter()
ds2 = minari.load_dataset("quack/toy-v0")
Xm, Mm, Am = [], [], []
for ep in ds2.iterate_episodes():
    Xm.append(ep.observations["observation"][:-1]); Mm.append(ep.observations["action_mask"][:-1]); Am.append(ep.actions)
Xm, Mm, Am = map(np.concatenate, (Xm, Mm, Am))
print("minari load s", round(time.perf_counter() - t0, 4), Xm.shape, Mm.shape, Am.shape,
      "equal to parquet:", bool(np.array_equal(Xm, X) and np.array_equal(Mm, M) and np.array_equal(Am, A)))

# --- Masked behaviour cloning step in plain PyTorch
import torch
net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], 64), torch.nn.ReLU(), torch.nn.Linear(64, M.shape[1]))
opt = torch.optim.Adam(net.parameters(), 1e-3)
xt, mt, at = torch.from_numpy(X), torch.from_numpy(M).bool(), torch.from_numpy(A).long()
for it in range(3):
    logits = net(xt).masked_fill(~mt, -1e9)
    loss = torch.nn.functional.cross_entropy(logits, at)
    opt.zero_grad(); loss.backward(); opt.step(); print("bc loss", round(loss.item(), 4))
```

</details>

## d3rlpy check (install and mask)

- Install: in a scratch copy of the project (outside the repo, `/tmp`), `uv add --group train d3rlpy` resolved 118 packages (104 in the lock before; 14 new) and chose d3rlpy 2.8.0 with `gymnasium` 1.4.0; `uv add --group train "d3rlpy==2.8.1"` installed 2.8.1 and replaced `gymnasium` 1.4.0 by 1.0.0 (`- gymnasium==1.4.0`, `+ gymnasium==1.0.0` in the output). The repo's own `pyproject.toml` and `uv.lock` were not touched.
- Mask: `curl -sL https://files.pythonhosted.org/packages/source/d/d3rlpy/d3rlpy-2.8.1.tar.gz`, unpacked, `grep -rniE "action_mask|legal|masked" d3rlpy-2.8.1/d3rlpy` finds a BCQ comment (`actions except the min value are masked`, `bcq_impl.py:298`), `masked_fill` in the transformer attention, and `action_masks` of the Decision Transformer (a flag for padded steps, `transformers.py:514`), none of them a legal-action mask on the output of a discrete policy. I did not train d3rlpy: with no mask, the question "does it choose only legal actions" is answered by its code, not by a run.

## Sources

- Minari: https://pypi.org/project/minari/0.5.4/ , https://pypi.org/pypi/minari/json , https://github.com/Farama-Foundation/Minari , https://minari.farama.org/
- d3rlpy: https://pypi.org/project/d3rlpy/2.8.1/ , https://github.com/takuseno/d3rlpy , https://github.com/takuseno/d3rlpy/blob/master/setup.py
- CORL: https://github.com/tinkoff-ai/CORL
- stable-baselines3 2.9.0 and sb3-contrib 2.9.0: https://pypi.org/project/stable-baselines3/2.9.0/ , https://pypi.org/project/sb3-contrib/2.9.0/
- torch 2.14.1 wheel size: https://pypi.org/pypi/torch/2.14.1/json
