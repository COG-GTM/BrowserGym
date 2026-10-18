import type { Meta, StoryObj } from "@storybook/react";
import { useEffect, useState } from "react";
import { failedChat, failedRun, failedSteps, flightBoxes, flightChat, flightRun, flightScreenshots, flightSteps } from "../../fixtures";
import { RunReplayPlayer } from "../components/RunReplayPlayer";
import type { Step } from "../types";

const screenshot = (s: Step) => flightScreenshots[s.index] ?? null;
const boxes = (i: number) => flightBoxes[i];

const meta: Meta<typeof RunReplayPlayer> = {
  title: "Trace Viewer/RunReplayPlayer",
  component: RunReplayPlayer,
  parameters: { layout: "padded" },
  args: {
    run: flightRun,
    steps: flightSteps,
    chat: flightChat,
    resolveScreenshotUrl: screenshot,
    getBoxes: boxes,
  },
};
export default meta;
type Story = StoryObj<typeof RunReplayPlayer>;

export const Succeeded: Story = { args: { initialIndex: 0 } };
export const SubmitStep: Story = { args: { initialIndex: 5 } };
export const FailedAction: Story = { args: { initialIndex: 3 } };
export const FailedRun: Story = {
  args: { run: failedRun, steps: failedSteps, chat: failedChat, initialIndex: 4 },
};
export const Mobile: Story = {
  args: { initialIndex: 6 },
  parameters: { viewport: { defaultViewport: "mobile2" } },
  decorators: [(S) => <div style={{ maxWidth: 414 }}><S /></div>],
};

function LiveRun() {
  const [n, setN] = useState(2);
  useEffect(() => {
    if (n >= flightSteps.length) return;
    const t = setTimeout(() => setN(n + 1), 2000);
    return () => clearTimeout(t);
  }, [n]);
  const steps = flightSteps.slice(0, n);
  const last = steps[steps.length - 1]!;
  return (
    <RunReplayPlayer
      run={{ ...flightRun, status: n >= flightSteps.length ? "succeeded" : "running", n_steps: n, finished_at: null, reward: null }}
      steps={steps}
      chat={flightChat.filter((m) => m.timestamp <= last.timestamp)}
      resolveScreenshotUrl={screenshot}
      getBoxes={boxes}
      initialIndex={n - 1}
    />
  );
}
export const Live: Story = { render: () => <LiveRun /> };
