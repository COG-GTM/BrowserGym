import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { flightSteps } from "../../fixtures";
import { StepTimeline } from "../components/StepTimeline";
import type { Step } from "../types";

function Controlled({ steps, initial }: { steps: Step[]; initial: number }) {
  const [i, setI] = useState(initial);
  return (
    <div className="stv-root" style={{ maxWidth: 720 }}>
      <StepTimeline steps={steps} currentIndex={i} onChange={setI} />
      <p style={{ fontSize: 12, color: "#677085" }}>Focus the track and use ←/→, PageUp/PageDown, Home/End, or drag to scrub.</p>
    </div>
  );
}

const meta: Meta<typeof Controlled> = {
  title: "Trace Viewer/StepTimeline",
  component: Controlled,
  args: { steps: flightSteps, initial: 3 },
};
export default meta;
type Story = StoryObj<typeof Controlled>;

export const Default: Story = {};
export const AtFailedStep: Story = { args: { initial: 3 } };
export const LongRun: Story = {
  args: {
    initial: 27,
    steps: Array.from({ length: 60 }, (_, i) => ({
      ...flightSteps[i % 8]!,
      index: i,
      terminated: i === 59,
      action: i === 59 ? null : flightSteps[i % 8]!.action,
    })),
  },
};
