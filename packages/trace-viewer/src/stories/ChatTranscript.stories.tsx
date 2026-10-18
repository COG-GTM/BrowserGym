import type { Meta, StoryObj } from "@storybook/react";
import { failedChat, flightChat, flightSteps } from "../../fixtures";
import { ChatTranscript } from "../components/ChatTranscript";

const meta: Meta<typeof ChatTranscript> = {
  title: "Trace Viewer/ChatTranscript",
  component: ChatTranscript,
  decorators: [(S) => <div className="stv-root" style={{ maxWidth: 480 }}><S /></div>],
  args: { messages: flightChat },
};
export default meta;
type Story = StoryObj<typeof ChatTranscript>;

export const Completed: Story = {};
export const SyncedToStep: Story = { args: { until: flightSteps[3]!.timestamp } };
export const Infeasible: Story = { args: { messages: failedChat } };
export const Empty: Story = { args: { messages: [] } };
