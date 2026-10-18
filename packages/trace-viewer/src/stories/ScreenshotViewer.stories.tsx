import type { Meta, StoryObj } from "@storybook/react";
import { flightBoxes, flightScreenshots } from "../../fixtures";
import { ScreenshotViewer } from "../components/ScreenshotViewer";

const meta: Meta<typeof ScreenshotViewer> = {
  title: "Trace Viewer/ScreenshotViewer",
  component: ScreenshotViewer,
  decorators: [(S) => <div className="stv-root" style={{ maxWidth: 820 }}><S /></div>],
  args: { src: flightScreenshots[0], alt: "Skyhop search form" },
};
export default meta;
type Story = StoryObj<typeof ScreenshotViewer>;

export const Plain: Story = {};
export const TargetOverlay: Story = {
  args: { src: flightScreenshots[0], boxes: flightBoxes[0], highlightBids: ["15"] },
};
export const SetOfMarks: Story = {
  args: { src: flightScreenshots[6], boxes: flightBoxes[6], highlightBids: ["44"], defaultOverlay: "som" },
};
export const HoverFromTree: Story = {
  args: { src: flightScreenshots[5], boxes: flightBoxes[5], highlightBids: ["30"], hoverBid: "21" },
};
export const TargetOffscreen: Story = {
  args: { src: flightScreenshots[3], boxes: flightBoxes[3], highlightBids: ["zz99"] },
};
export const NoScreenshot: Story = { args: { src: null } };
