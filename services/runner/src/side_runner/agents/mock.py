import time

from .base import Agent, AgentOutput


class MockAgent(Agent):
    """Deterministic, offline agent: noop, scroll, then ``send_msg_to_user('done')``.

    Any user message that arrives via the inbox is acknowledged first with
    ``send_msg_to_user('Received: <msg>')``.

    Optional agent-json knobs (handy for demos and tests):
      ``delay_ms``     sleep before every decision (makes live viewing visible)
      ``fail_at_step`` raise an error when asked for action number N (1-based)
      ``final_message`` text of the final message (default ``done``)
    """

    type = "mock"
    title = "Mock agent (deterministic, offline)"
    PLAN = ("noop(200)", "scroll(0, 200)")

    def __init__(self, config):
        super().__init__(config)
        self.delay_ms = float(self.config.get("delay_ms") or 0)
        self.fail_at_step = self.config.get("fail_at_step")
        self.final_message = str(self.config.get("final_message") or "done")
        self.n_calls = 0
        self.plan_index = 0
        self.n_user_msgs_seen = None

    def get_action(self, obs: dict) -> AgentOutput:
        self.n_calls += 1
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        if self.fail_at_step is not None and self.n_calls >= int(self.fail_at_step):
            raise RuntimeError(f"mock agent failure requested at step {self.n_calls}")

        user_msgs = [m for m in obs.get("chat_messages", ()) if m["role"] == "user"]
        if self.n_user_msgs_seen is None:
            # the goal is echoed as user message(s) at reset; it is not something to acknowledge
            self.n_user_msgs_seen = len(obs.get("goal_object", ()))
        if len(user_msgs) > self.n_user_msgs_seen:
            msg = user_msgs[self.n_user_msgs_seen]["message"]
            self.n_user_msgs_seen += 1
            return AgentOutput(
                action=f"send_msg_to_user({('Received: ' + msg)!r})",
                thought="A new user message arrived; acknowledging it.",
            )

        if self.plan_index < len(self.PLAN):
            action = self.PLAN[self.plan_index]
            self.plan_index += 1
            return AgentOutput(action=action, thought=f"Mock step {self.plan_index}: {action}")

        return AgentOutput(
            action=f"send_msg_to_user({self.final_message!r})",
            thought="Mock plan complete; reporting to the user.",
            done=True,
        )
