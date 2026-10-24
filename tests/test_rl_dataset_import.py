import subprocess
import sys


def test_dataset_module_imports_without_torch():
    code = (
        "import sys; import quack_rl.rl.dataset; "
        "sys.exit(1 if any(m == 'torch' or m.startswith('torch.') for m in sys.modules) else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
