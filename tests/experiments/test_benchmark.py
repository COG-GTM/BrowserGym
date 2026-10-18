import dataclasses
import os
import random
import re
import tempfile
import typing

import numpy as np
import pandas as pd
import pytest

from browsergym.core.action.base import AbstractActionSet
from browsergym.experiments.agent import Agent
from browsergym.experiments.benchmark import Benchmark, HighLevelActionSetArgs
from browsergym.experiments.benchmark.base import BenchmarkBackend
from browsergym.experiments.benchmark.configs import DEFAULT_BENCHMARKS
from browsergym.experiments.benchmark.utils import make_env_args_list_from_fixed_seeds
from browsergym.experiments.loop import AbstractAgentArgs, ExpArgs, get_exp_result
from browsergym.utils.obs import flatten_axtree_to_str


class MiniwobTestAgent(Agent):

    def __init__(self, action_set: AbstractActionSet):
        self.action_set = action_set

    def obs_preprocessor(self, obs: dict):
        return {"axtree_txt": flatten_axtree_to_str(obs["axtree_object"])}

    def get_action(self, obs: dict) -> tuple[str, dict]:
        match = re.search(r"^\s*\[(\d+)\].*button", obs["axtree_txt"], re.MULTILINE | re.IGNORECASE)

        if match:
            bid = match.group(1)
            action = f'click("{bid}")'
        else:
            raise Exception("Can't find the button's bid")

        return action, dict(think="I'm clicking the button as requested.")


@dataclasses.dataclass
class MiniwobTestAgentArgs(AbstractAgentArgs):
    high_level_action_set: HighLevelActionSetArgs = None

    def make_agent(self):
        return MiniwobTestAgent(action_set=self.high_level_action_set.make_action_set())


def test_build_benchmarks():
    expected_bench_size = {
        "miniwob": 125 * 5,
        "miniwob_tiny_test": 2 * 2,
        "webarena": 812,
        "webarena_tiny": 6,
        "webarena_lite": 165,
        "visualwebarena": 910,
        "visualwebarena_tiny": 4,
        "workarena_l1": 33 * 10,
        "workarena_l2_agent_curriculum_eval": 235,
        "workarena_l3_agent_curriculum_eval": 235,
        "assistantbench": 214,
        "weblinx": 31586,
    }
    for name, benchmark_builder in DEFAULT_BENCHMARKS.items():
        benchmark = benchmark_builder()
        assert name == benchmark.name
        assert benchmark.env_args_list  # non-empty
        assert benchmark.task_metadata is not None
        assert len(benchmark.env_args_list) == expected_bench_size[name]
        benchmark_bis = Benchmark.from_json(benchmark.to_json())
        assert benchmark.to_dict() == benchmark_bis.to_dict()


def test_benchmark_subset():
    benchmark: Benchmark = DEFAULT_BENCHMARKS["miniwob"]()

    benchmark_subset = benchmark.subset_from_regexp(column="task_name", regexp="click")
    assert len(benchmark_subset.env_args_list) == 31 * 5
    assert benchmark_subset.name == "miniwob[task_name=/click/]"

    benchmark_subset_1 = benchmark_subset.subset_from_regexp(
        column="miniwob_category", regexp="original"
    )
    benchmark_subset_2 = benchmark_subset.subset_from_glob(
        column="miniwob_category", glob="original"
    )

    assert benchmark_subset_1.name == "miniwob[task_name=/click/][miniwob_category=/original/]"
    assert benchmark_subset_2.name == "miniwob[task_name=/click/][miniwob_category=original]"

    dict_1 = benchmark_subset_1.to_dict()
    dict_1.pop("name")
    dict_2 = benchmark_subset_2.to_dict()
    dict_2.pop("name")

    assert dict_1 == dict_2


def test_benchmark_subset_from_task_ratio():
    benchmark: Benchmark = DEFAULT_BENCHMARKS["webarena"]()

    # Store initial random state
    initial_state = random.getstate()

    benchmark_subset = benchmark.subset_from_task_ratio(ratio=0.5, seed=1)
    assert len(benchmark_subset.env_args_list) == 812 // 2
    assert benchmark_subset.name == "webarena[ratio=0.5, seed=1]"

    # Verify global random state hasn't changed
    assert random.getstate() == initial_state

    benchmark_subset_1 = benchmark_subset.subset_from_task_ratio(ratio=0.5, seed=1)
    benchmark_subset_2 = benchmark_subset.subset_from_task_ratio(ratio=0.5, seed=2)

    # Verify global random state still hasn't changed
    assert random.getstate() == initial_state

    # Check the task lists are different
    assert not np.all(
        [
            env_args.task_name == env_args_2.task_name
            for env_args, env_args_2 in zip(
                benchmark_subset_1.env_args_list, benchmark_subset_2.env_args_list
            )
        ]
    )

    dict_1 = benchmark_subset_1.to_dict()
    dict_1.pop("name")
    dict_2 = benchmark_subset_2.to_dict()
    dict_2.pop("name")
    assert len(dict_1["env_args_list"]) == len(dict_2["env_args_list"])
    assert dict_1 != dict_2


def test_prepare_backend_miniwob():
    MINIWOB_URL = os.environ["MINIWOB_URL"]
    try:
        benchmark: Benchmark = DEFAULT_BENCHMARKS["miniwob"]()

        benchmark.prepare_backends()

        del os.environ["MINIWOB_URL"]
        with pytest.raises(Exception):
            benchmark.prepare_backends()

        os.environ["MINIWOB_URL"] = ""
        with pytest.raises(Exception):
            benchmark.prepare_backends()
    finally:
        os.environ["MINIWOB_URL"] = MINIWOB_URL


def test_prepare_backend_assistantbench():
    benchmark: Benchmark = DEFAULT_BENCHMARKS["assistantbench"]()
    benchmark.prepare_backends()


@pytest.mark.skip
def test_prepare_backend_webarena():
    WA_FULL_RESET = os.environ["WA_FULL_RESET"]
    try:
        benchmark: Benchmark = DEFAULT_BENCHMARKS["webarena"]()

        benchmark.prepare_backends()

        del os.environ["WA_FULL_RESET"]
        with pytest.raises(Exception):
            benchmark.prepare_backends()

        os.environ["WA_FULL_RESET"] = "http://localhost:12345/reset"
        with pytest.raises(Exception):
            benchmark.prepare_backends()
    finally:
        os.environ["WA_FULL_RESET"] = WA_FULL_RESET


@pytest.mark.skip
def test_prepare_backend_visualwebarena():
    VWA_FULL_RESET = os.environ["VWA_FULL_RESET"]
    try:
        benchmark: Benchmark = DEFAULT_BENCHMARKS["visualwebarena"]()

        benchmark.prepare_backends()

        del os.environ["VWA_FULL_RESET"]
        with pytest.raises(Exception):
            benchmark.prepare_backends()

        os.environ["VWA_FULL_RESET"] = "http://localhost:12345/reset"
        with pytest.raises(Exception):
            benchmark.prepare_backends()
    finally:
        os.environ["VWA_FULL_RESET"] = VWA_FULL_RESET


@pytest.mark.skip
def test_prepare_backend_weblinx():
    BROWSERGYM_WEBLINX_CACHE_DIR = os.environ["BROWSERGYM_WEBLINX_CACHE_DIR"]
    try:
        benchmark: Benchmark = DEFAULT_BENCHMARKS["weblinx"]()

        benchmark.prepare_backends()

        del os.environ["BROWSERGYM_WEBLINX_CACHE_DIR"]
        with pytest.raises(Exception):
            benchmark.prepare_backends()

    finally:
        os.environ["BROWSERGYM_WEBLINX_CACHE_DIR"] = BROWSERGYM_WEBLINX_CACHE_DIR


def test_run_mock_benchmark():
    benchmark = Benchmark(
        name="miniwob_click_test",
        high_level_action_set_args=HighLevelActionSetArgs(
            subsets=["bid"],
            multiaction=False,
            strict=False,
            retry_with_force=True,
            demo_mode="off",
        ),
        is_multi_tab=False,
        supports_parallel_seeds=True,
        backends=["miniwob"],
        env_args_list=make_env_args_list_from_fixed_seeds(
            task_list=["miniwob.click-test"],
            max_steps=5,
            fixed_seeds=[0, 1],
        ),
    )

    for env_args in benchmark.env_args_list:
        agent_args = MiniwobTestAgentArgs(
            high_level_action_set=benchmark.high_level_action_set_args
        )
        exp_args = ExpArgs(
            agent_args=agent_args,
            env_args=env_args,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            exp_args.prepare(tmp_dir)
            exp_args.run()
            exp_result = get_exp_result(exp_args.exp_dir)
            exp_record = exp_result.get_exp_record()

            target = {
                "env_args.task_name": "miniwob.click-test",
                "env_args.headless": True,
                "env_args.record_video": False,
                "n_steps": 1,
                "cum_reward": 1.0,
                "terminated": True,
                "truncated": False,
            }

            assert len(exp_result.steps_info) == 2

            for key, target_val in target.items():
                assert key in exp_record
                assert exp_record[key] == target_val


def test_dependency_graphs():
    benchmark = Benchmark(
        name="my_bench",
        high_level_action_set_args=HighLevelActionSetArgs(
            subsets=["bid"],
            multiaction=False,
            strict=False,
            retry_with_force=True,
            demo_mode="off",
        ),
        is_multi_tab=False,
        supports_parallel_seeds=True,
        backends=["miniwob"],
        env_args_list=make_env_args_list_from_fixed_seeds(
            task_list=["miniwob.click-test"],
            max_steps=5,
            fixed_seeds=[0, 1],
        ),
    )

    # one task, two seeds
    task_dependencies = benchmark.dependency_graph_over_tasks()
    assert task_dependencies == {"miniwob.click-test": []}

    env_args_dependencies = benchmark.dependency_graphs_over_env_args()
    assert env_args_dependencies == [{0: [], 1: []}]

    # change to no parallel seed support
    benchmark.supports_parallel_seeds = False
    env_args_dependencies = benchmark.dependency_graphs_over_env_args()
    assert env_args_dependencies == [{0: []}, {1: []}]

    # webarena, 3 tasks x 1 seed
    benchmark = DEFAULT_BENCHMARKS["webarena"]().subset_from_regexp(
        column="task_name", regexp=r"^webarena\.[012]$"
    )

    task_dependencies = benchmark.dependency_graph_over_tasks()
    assert task_dependencies == {
        "webarena.0": [],
        "webarena.1": ["webarena.0"],
        "webarena.2": ["webarena.1"],
    }

    env_args_dependencies = benchmark.dependency_graphs_over_env_args()
    assert env_args_dependencies == [{0: [], 1: [0], 2: [1]}]

    # workarena L2, 2 task x (2 seeds, 1 seed)
    benchmark = DEFAULT_BENCHMARKS["workarena_l2_agent_curriculum_eval"]().subset_from_regexp(
        column="task_name",
        regexp=r"^workarena\.servicenow\.workload-balancing-small-l2$|^workarena\.servicenow\.easy-expense-management-small-l2$",
    )

    task_dependencies = benchmark.dependency_graph_over_tasks()
    assert task_dependencies == {
        "workarena.servicenow.workload-balancing-small-l2": [],
        "workarena.servicenow.easy-expense-management-small-l2": [],
    }

    env_args_dependencies = benchmark.dependency_graphs_over_env_args()
    assert env_args_dependencies == [{0: [], 1: [], 2: []}]

    # change to no parallel seed support
    benchmark.supports_parallel_seeds = False
    env_args_dependencies = benchmark.dependency_graphs_over_env_args()
    assert env_args_dependencies == [{0: [], 2: []}, {1: []}]

    # webarena, 6 dependent tasks x 1 seed
    benchmark = DEFAULT_BENCHMARKS["webarena"]().subset_from_regexp(
        column="task_name",
        regexp=r"^webarena\.533$|^webarena\.537$|^webarena\.552$|^webarena\.410$|^webarena\.561$|^webarena\.562$",
    )

    task_dependencies = benchmark.dependency_graph_over_tasks()
    assert {k: set(v) for k, v in task_dependencies.items()} == {
        k: set(v)
        for k, v in {
            "webarena.410": [],
            "webarena.533": [],
            "webarena.537": ["webarena.533"],
            "webarena.552": ["webarena.410", "webarena.537"],
            "webarena.561": ["webarena.552"],
            "webarena.562": ["webarena.552", "webarena.561"],
        }.items()
    }

    env_args_dependencies = benchmark.dependency_graphs_over_env_args()
    assert [{k: set(v) for k, v in deps.items()} for deps in env_args_dependencies] == [
        {k: set(v) for k, v in {0: [], 1: [], 2: [1], 3: [0, 2], 4: [3], 5: [3, 4]}.items()}
    ]


def _make_split_benchmark(task_metadata="default", backends=("miniwob",)):
    task_splits = {
        "fake.task-a": "train",
        "fake.task-b": "train",
        "fake.task-c": "valid",
        "fake.task-d": "test",
        "fake.task-e": "pretrain",
        "fake.task-f": "test_extra",
    }
    if isinstance(task_metadata, str) and task_metadata == "default":
        task_metadata = pd.DataFrame(
            [
                {"task_name": task_name, "browsergym_split": split}
                for task_name, split in task_splits.items()
            ]
        )
    return Benchmark(
        name="fake_bench",
        high_level_action_set_args=HighLevelActionSetArgs(subsets=["bid"]),
        is_multi_tab=False,
        supports_parallel_seeds=True,
        backends=list(backends),
        env_args_list=make_env_args_list_from_fixed_seeds(
            task_list=list(task_splits.keys()),
            max_steps=5,
            fixed_seeds=[0, 1],
        ),
        task_metadata=task_metadata,
    )


def _task_names(benchmark: Benchmark):
    return [env_args.task_name for env_args in benchmark.env_args_list]


def test_benchmark_subset_from_list():
    benchmark = _make_split_benchmark()

    subset = benchmark.subset_from_list(["fake.task-c", "fake.task-a"], split="train")
    assert subset.name == "fake_bench_custom_train"
    assert _task_names(subset) == ["fake.task-a", "fake.task-a", "fake.task-c", "fake.task-c"]
    assert [env_args.task_seed for env_args in subset.env_args_list] == [0, 1, 0, 1]
    assert subset.high_level_action_set_args == benchmark.high_level_action_set_args
    assert subset.is_multi_tab == benchmark.is_multi_tab
    assert subset.supports_parallel_seeds == benchmark.supports_parallel_seeds
    assert subset.backends == benchmark.backends
    assert subset.task_metadata is benchmark.task_metadata

    # the original benchmark is left untouched
    assert len(benchmark.env_args_list) == 12

    # default suffix, no split
    subset = benchmark.subset_from_list(["fake.task-d"])
    assert subset.name == "fake_bench_custom"
    assert _task_names(subset) == ["fake.task-d", "fake.task-d"]

    # custom suffix, duplicates in the task list are not duplicated in the subset
    subset = benchmark.subset_from_list(
        ["fake.task-b", "fake.task-b"], benchmark_name_suffix="mine"
    )
    assert subset.name == "fake_bench_mine"
    assert _task_names(subset) == ["fake.task-b", "fake.task-b"]

    # serialization round trip
    assert Benchmark.from_json(subset.to_json()).to_dict() == subset.to_dict()


def test_benchmark_subset_from_list_empty():
    benchmark = _make_split_benchmark()

    with pytest.raises(ValueError, match="Task list cannot be empty"):
        benchmark.subset_from_list([])


def test_benchmark_subset_from_list_unknown_task():
    benchmark = _make_split_benchmark()

    with pytest.raises(ValueError, match="do not exist in the benchmark") as exc_info:
        benchmark.subset_from_list(["fake.task-a", "fake.does-not-exist"])
    assert "fake.does-not-exist" in str(exc_info.value)
    assert "fake.task-a'" not in str(exc_info.value)

    # task present in the metadata but not in env_args_list is rejected too
    benchmark = benchmark.subset_from_list(["fake.task-a"])
    with pytest.raises(ValueError, match="do not exist in the benchmark"):
        benchmark.subset_from_list(["fake.task-b"])


def test_benchmark_subset_from_split():
    benchmark = _make_split_benchmark()

    train = benchmark.subset_from_split("train")
    assert train.name == "fake_bench_train"
    # exact match only: "pretrain" must not leak into train
    assert _task_names(train) == ["fake.task-a", "fake.task-a", "fake.task-b", "fake.task-b"]

    valid = benchmark.subset_from_split("valid")
    assert valid.name == "fake_bench_valid"
    assert _task_names(valid) == ["fake.task-c", "fake.task-c"]

    test = benchmark.subset_from_split("test")
    assert test.name == "fake_bench_test"
    # exact match only: "test_extra" must not leak into test
    assert _task_names(test) == ["fake.task-d", "fake.task-d"]

    # splits are disjoint
    assert not set(_task_names(train)) & set(_task_names(valid))
    assert not set(_task_names(train)) & set(_task_names(test))
    assert not set(_task_names(valid)) & set(_task_names(test))


def test_benchmark_subset_from_split_missing_column():
    benchmark = _make_split_benchmark(task_metadata=None)

    with pytest.raises(NotImplementedError, match="browsergym_split"):
        benchmark.subset_from_split("train")


def test_benchmark_subset_from_split_empty():
    benchmark = _make_split_benchmark()

    # metadata still has a "valid" row, but no env_args left for it
    benchmark = benchmark.subset_from_list(["fake.task-a", "fake.task-d"])
    with pytest.raises(ValueError, match="default valid split for this benchmark is empty"):
        benchmark.subset_from_split("valid")

    task_metadata = pd.DataFrame(
        [{"task_name": f"fake.task-{letter}", "browsergym_split": "train"} for letter in "abcdef"]
    )
    benchmark = _make_split_benchmark(task_metadata=task_metadata)
    with pytest.raises(ValueError, match="default test split for this benchmark is empty"):
        benchmark.subset_from_split("test")


def test_benchmark_unknown_backend():
    with pytest.raises(ValueError, match="Unknown Benchmark backend 'bogus'"):
        _make_split_benchmark(backends=["miniwob", "bogus"])

    # every declared backend is accepted
    for backend in typing.get_args(BenchmarkBackend):
        assert _make_split_benchmark(backends=[backend]).backends == [backend]


def test_benchmark_default_task_metadata():
    benchmark = _make_split_benchmark(task_metadata=None)

    assert list(benchmark.task_metadata.columns) == ["task_name"]
    assert sorted(benchmark.task_metadata["task_name"]) == [
        f"fake.task-{letter}" for letter in "abcdef"
    ]
    # one row per unique task, not per env_args
    assert len(benchmark.task_metadata) == 6

    # default metadata still supports column-based subsetting
    subset = benchmark.subset_from_regexp(column="task_name", regexp=r"task-[ab]$")
    assert sorted(set(_task_names(subset))) == ["fake.task-a", "fake.task-b"]


def test_benchmark_metadata_must_cover_env_args():
    task_metadata = pd.DataFrame([{"task_name": "fake.task-a", "browsergym_split": "train"}])

    with pytest.raises(AssertionError):
        _make_split_benchmark(task_metadata=task_metadata)


def test_benchmark_subset_from_task_ratio_zero_tasks():
    benchmark = _make_split_benchmark()

    # int(6 * 0.1) == 0: an empty subset is returned without error
    subset = benchmark.subset_from_task_ratio(ratio=0.1, seed=0)
    assert subset.env_args_list == []

    subset = benchmark.subset_from_task_ratio(ratio=1.0, seed=0)
    assert sorted(_task_names(subset)) == sorted(_task_names(benchmark))
