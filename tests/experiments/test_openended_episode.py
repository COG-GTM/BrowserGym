import dataclasses
from pathlib import Path

from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.experiments.agent import Agent, AgentInfo
from browsergym.experiments.loop import AbstractAgentArgs, EnvArgs, ExpArgs, ExpResult


class SayHiAgent(Agent):
    """Trivial offline agent: sends one chat message, then ends the episode."""

    action_set = HighLevelActionSet(subsets=["chat", "bid"])

    def __init__(self) -> None:
        self.n_actions = 0

    def obs_preprocessor(self, obs: dict) -> dict:
        return {key: obs[key] for key in ("goal_object", "url", "screenshot", "chat_messages")}

    def get_action(self, obs: dict) -> tuple[str | None, AgentInfo]:
        self.n_actions += 1
        if self.n_actions == 1:
            return 'send_msg_to_user("hi")', AgentInfo(think="greet the user")
        return None, AgentInfo(think="done")


@dataclasses.dataclass
class SayHiAgentArgs(AbstractAgentArgs):
    def make_agent(self) -> Agent:
        return SayHiAgent()


def test_openended_episode_end_to_end(tmp_path: Path):
    exp_args = ExpArgs(
        agent_args=SayHiAgentArgs(),
        env_args=EnvArgs(
            task_name="openended",
            task_seed=0,
            max_steps=5,
            task_kwargs={"start_url": "about:blank", "goal": "say hi"},
        ),
    )
    exp_args.prepare(tmp_path)
    exp_args.run()

    exp_dir = Path(exp_args.exp_dir)
    files = sorted(p.name for p in exp_dir.iterdir())
    for expected in (
        "exp_args.pkl",
        "experiment.log",
        "goal_object.pkl.gz",
        "package_versions.txt",
        "screenshot_step_0.png",
        "screenshot_step_1.png",
        "step_0.pkl.gz",
        "step_1.pkl.gz",
        "summary_info.json",
    ):
        assert expected in files
    assert not [name for name in files if name.endswith(".tmp")]

    result = ExpResult(exp_dir)
    assert result.status == "done"
    assert result.summary_info["err_msg"] is None
    assert result.summary_info["n_steps"] == 1
    assert result.summary_info["truncated"] is True
    steps = result.steps_info
    assert [s.action for s in steps] == ['send_msg_to_user("hi")', None]
    assert steps[1].obs["chat_messages"][-1]["message"] == "hi"
    assert steps[1].obs["screenshot"].ndim == 3
