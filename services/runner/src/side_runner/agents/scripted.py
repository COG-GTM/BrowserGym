from .base import Agent, AgentOutput


class ScriptedAgent(Agent):
    """Replays ``agent-json.actions`` (list of BrowserGym action strings), then stops."""

    type = "scripted"
    title = "Scripted agent (replays a list of actions)"

    def __init__(self, config):
        super().__init__(config)
        actions = self.config.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError("scripted agent requires a non-empty 'actions' list in agent-json")
        if not all(isinstance(a, str) and a.strip() for a in actions):
            raise ValueError("scripted agent 'actions' must be non-empty strings")
        self.actions = list(actions)
        self.index = 0

    def get_action(self, obs: dict) -> AgentOutput:
        action = self.actions[self.index]
        self.index += 1
        return AgentOutput(
            action=action,
            thought=f"Scripted action {self.index}/{len(self.actions)}",
            done=self.index >= len(self.actions),
        )
