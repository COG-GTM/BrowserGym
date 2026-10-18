import type { Meta, StoryObj } from "@storybook/react";
import { flightSteps } from "../../fixtures";
import { AXTreeViewer } from "../components/AXTreeViewer";

const meta: Meta<typeof AXTreeViewer> = {
  title: "Trace Viewer/AXTreeViewer",
  component: AXTreeViewer,
  decorators: [(S) => <div className="stv-root" style={{ maxWidth: 560, height: 520, border: "1px solid #dfe3ea", borderRadius: 8 }}><S /></div>],
  args: { axtree: flightSteps[5]!.axtree_txt, highlightBid: "30", focusedBid: flightSteps[5]!.focused_element_bid },
};
export default meta;
type Story = StoryObj<typeof AXTreeViewer>;

export const HighlightActionTarget: Story = {};
export const Search: Story = { args: { axtree: flightSteps[6]!.axtree_txt, highlightBid: "44", defaultQuery: "select" } };
export const Collapsed: Story = { args: { defaultExpandDepth: 2, highlightBid: null } };
export const Empty: Story = { args: { axtree: null, highlightBid: null } };
