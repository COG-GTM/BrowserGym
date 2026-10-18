import dataclasses
from typing import Any, Optional

from browsergym.core.action.highlevel import HighLevelActionSet

AGENT_CONFIG_DEFAULTS = {"model": None, "use_screenshot": False, "use_axtree": True}


@dataclasses.dataclass
class AgentOutput:
    """One agent decision.

    action: BrowserGym high-level action string, e.g. ``click('a42')``.
    thought: optional free-text reasoning shown in the trace.
    done: the agent considers the episode finished once this action has been executed.
    """

    action: str
    thought: Optional[str] = None
    done: bool = False


def default_action_set() -> HighLevelActionSet:
    return HighLevelActionSet(
        subsets=["chat", "tab", "nav", "bid", "infeas"],
        strict=False,
        multiaction=False,
    )


class Agent:
    """Base class for Side agents.

    ``obs`` passed to :meth:`get_action` is the BrowserGym observation augmented with
    ``axtree_txt`` and ``pruned_html`` (see :func:`side_runner.obs.preprocess_obs`).
    """

    type: str = ""
    title: str = ""
    models: tuple[str, ...] = ()

    def __init__(self, config: dict[str, Any]):
        self.config = {**AGENT_CONFIG_DEFAULTS, **config}
        self.action_set = default_action_set()

    def get_action(self, obs: dict) -> AgentOutput:
        raise NotImplementedError

    def close(self) -> None:
        pass
