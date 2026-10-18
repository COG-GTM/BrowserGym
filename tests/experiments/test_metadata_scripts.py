import io
import os
import subprocess
import sys

import pandas as pd

from browsergym.experiments.benchmark.metadata.utils import task_metadata
from browsergym.experiments.benchmark.metadata import scripts

STRING_GROUPS_SPLIT = """
from browsergym.experiments.benchmark.metadata import scripts

task_metadata = scripts.task_metadata


def string_groups(benchmark_name):
    metadata = task_metadata(benchmark_name)
    metadata["similarity_group"] = "group-" + metadata["similarity_group"].astype(str)
    return metadata


scripts.task_metadata = string_groups
scripts.print_miniwob_train_test_splits()
"""


def _split_csv(output: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(output[output.index("task_name") :])).fillna("")


def test_miniwob_split_reproduces_published_metadata(capsys):
    scripts.print_miniwob_train_test_splits()
    split = _split_csv(capsys.readouterr().out)
    published = task_metadata("miniwob")

    assert list(split["task_name"]) == list(published["task_name"])
    assert list(split["browsergym_split"]) == list(published["browsergym_split"])


def test_miniwob_split_independent_of_hash_seed():
    outputs = []
    for hash_seed in ("0", "1", "1337"):
        result = subprocess.run(
            [sys.executable, "-c", STRING_GROUPS_SPLIT],
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(result.stdout)

    assert outputs[0] == outputs[1] == outputs[2]
