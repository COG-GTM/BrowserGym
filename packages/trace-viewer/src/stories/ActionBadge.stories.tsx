import type { Meta, StoryObj } from "@storybook/react";
import { sampleActions } from "../../fixtures";
import { ActionBadge } from "../components/ActionBadge";

const meta: Meta<typeof ActionBadge> = {
  title: "Trace Viewer/ActionBadge",
  component: ActionBadge,
  args: { action: "fill('b12', 'hello world')" },
};
export default meta;
type Story = StoryObj<typeof ActionBadge>;

export const Fill: Story = {};
export const Click: Story = { args: { action: "click('a42')" } };
export const Failed: Story = { args: { action: "click('zz99')", error: true } };
export const Compact: Story = { args: { action: "fill('b12', 'hello world')", compact: true } };

export const AllActions: Story = {
  render: () => (
    <div className="stv-root" style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "8px 16px", alignItems: "center" }}>
      {[...sampleActions, null].map((a, i) => (
        <div key={i} style={{ display: "contents" }}>
          <code style={{ fontSize: 12, color: "#677085" }}>{a ?? "null"}</code>
          <span>
            <ActionBadge action={a} />
          </span>
        </div>
      ))}
    </div>
  ),
};
