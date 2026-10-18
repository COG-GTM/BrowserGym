"""Builds a saved experiment directory with the pre-modernization serialization code.

The pickles under ``tests/experiments/data/legacy_exp`` were produced from the repository root
with ``python -c "from tests.experiments.legacy_fixtures import build; build()"`` against
browsergym-experiments 0.14.3.dev1 (before the modernization of ``loop.py``). They are committed so that tests can check that
results saved by older versions keep loading. Do not regenerate them with newer code.
"""

import dataclasses
import pickle
import shutil
from pathlib import Path

import numpy as np

from browsergym.experiments.agent import Agent, AgentInfo
from browsergym.experiments.loop import AbstractAgentArgs, EnvArgs, ExpArgs, StepInfo

LEGACY_EXP_DIR = Path(__file__).parent / "data" / "legacy_exp"


class LegacyNoopAgent(Agent):
    def get_action(self, obs):
        return "noop()", AgentInfo(think="waiting")


@dataclasses.dataclass
class LegacyNoopAgentArgs(AbstractAgentArgs):
    def make_agent(self):
        return LegacyNoopAgent()


def build(exp_dir: Path = LEGACY_EXP_DIR) -> None:
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    exp_dir.mkdir(parents=True)

    exp_args = ExpArgs(
        agent_args=LegacyNoopAgentArgs(),
        env_args=EnvArgs(task_name="openended", task_seed=7, max_steps=3),
        exp_name="legacy_fixture",
    )
    exp_args.exp_id = "00000000-0000-0000-0000-000000000000"
    exp_args.exp_dir = exp_dir
    with open(exp_dir / "exp_args.pkl", "wb") as f:
        pickle.dump(exp_args, f)

    screenshot = np.zeros((4, 4, 3), dtype=np.uint8)
    screenshot[0, 0] = [255, 0, 0]
    episode = []
    for step in range(2):
        step_info = StepInfo(step=step)
        step_info.obs = {
            "goal": "say hi",
            "goal_object": [{"type": "text", "text": "say hi"}],
            "url": "about:blank",
            "screenshot": screenshot,
            "axtree_txt": "RootWebArea ''",
        }
        step_info.reward = float(step)
        step_info.raw_reward = float(step)
        step_info.terminated = step == 1
        step_info.truncated = False
        step_info.action = None if step == 1 else 'send_msg_to_user("hi")'
        step_info.agent_info = AgentInfo(think="say hi", extra_info={"k": 1}, stats={})
        step_info.stats = {"n_token_goal": 2, "step_elapsed": 0.5, "agent_elapsed": 0.25}
        step_info.task_info = {"step": step}
        step_info.profiling.env_start = 1.0 + step
        step_info.profiling.env_stop = 1.5 + step
        step_info.save_step_info(exp_dir, save_screenshot=True)
        episode.append(step_info)

    exp_args.save_summary_info(episode, exp_dir, None, None)
    (exp_dir / "experiment.log").write_text("legacy fixture\n")
