import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import step0 from "../../fixtures/flight-search/steps/0.json";
import step5 from "../../fixtures/flight-search/steps/5.json";
import { flightRun } from "../../fixtures";
import type { StepDetail } from "../types";
import { ActionBadge } from "./ActionBadge";
import { AXTreeViewer } from "./AXTreeViewer";
import { ChatTranscript } from "./ChatTranscript";
import { RunReplayPlayer } from "./RunReplayPlayer";
import { ScreenshotViewer } from "./ScreenshotViewer";

describe("ActionBadge", () => {
  it("renders name, bid and text", () => {
    const onBidClick = vi.fn();
    render(<ActionBadge action="fill('b12', 'hello')" onBidClick={onBidClick} />);
    expect(screen.getByText("fill")).toBeInTheDocument();
    expect(screen.getByText("hello")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Element b12" }));
    expect(onBidClick).toHaveBeenCalledWith("b12");
  });

  it("falls back for null and unparsable actions", () => {
    const { rerender, container } = render(<ActionBadge action={null} />);
    expect(screen.getByText("no action")).toBeInTheDocument();
    rerender(<ActionBadge action="click('a42'" />);
    expect(container.firstChild).toHaveAttribute("data-category", "invalid");
  });
});

describe("ActionBadge multi-action", () => {
  it("renders one badge per call with every bid", () => {
    render(<ActionBadge action={"fill('1', 'Paris')\nclick('2')"} />);
    expect(screen.getByText("fill")).toBeInTheDocument();
    expect(screen.getByText("click")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Element 2" })).toBeInTheDocument();
  });
});

describe("AXTreeViewer", () => {
  it("highlights the bid referenced by the action", () => {
    const { container } = render(<AXTreeViewer axtree={step5.axtree_txt} highlightBid="30" focusedBid="29" />);
    const hl = container.querySelector(".stv-axnode--highlight")!;
    expect(hl).toHaveAttribute("data-bid", "30");
    expect(hl).toHaveTextContent("button'Search flights'");
    expect(container.querySelector(".stv-axnode--focused")).toHaveAttribute("data-bid", "29");
  });

  it("filters by search query and keeps ancestors", async () => {
    const user = userEvent.setup();
    render(<AXTreeViewer axtree={step5.axtree_txt} />);
    await user.type(screen.getByRole("searchbox"), "lisbon");
    expect(screen.getByText("2 matches")).toBeInTheDocument();
    const tree = screen.getByRole("tree");
    const items = within(tree).getAllByRole("treeitem");
    expect(items.map((i) => i.getAttribute("data-bid") ?? i.textContent?.trim().split(" ")[0])).toContain("17");
    expect(within(tree).queryByText("'Search flights'")).not.toBeInTheDocument();
  });

  it("collapses and expands with the keyboard and selects bids", async () => {
    const user = userEvent.setup();
    const onSelectBid = vi.fn();
    render(<AXTreeViewer axtree={step0.axtree_txt} onSelectBid={onSelectBid} />);
    const banner = screen.getAllByRole("treeitem").find((el) => el.getAttribute("data-bid") === "6")!;
    expect(banner).toHaveAttribute("aria-expanded", "true");
    banner.focus();
    await user.keyboard("{ArrowLeft}");
    expect(banner).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("'Hotels'")).not.toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByText("'Hotels'")).toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(onSelectBid).toHaveBeenCalledWith("6");
  });
});

describe("ChatTranscript", () => {
  it("dims messages after the replay position", () => {
    render(
      <ChatTranscript
        until="2026-10-18T02:40:10Z"
        messages={[
          { role: "user", message: "go", timestamp: "2026-10-18T02:40:00Z" },
          { role: "assistant", message: "done", timestamp: "2026-10-18T02:40:20Z" },
        ]}
      />,
    );
    expect(screen.getByText("go").closest("li")).not.toHaveClass("stv-msg--future");
    expect(screen.getByText("done").closest("li")).toHaveClass("stv-msg--future");
  });
});

describe("ScreenshotViewer", () => {
  it("draws the target box and zooms", () => {
    const { container } = render(
      <ScreenshotViewer
        src="data:image/png;base64,AA=="
        naturalSize={{ width: 800, height: 520 }}
        boxes={[
          { bid: "15", bbox: [40, 105, 227, 34] },
          { bid: "30", bbox: [171, 219, 129, 36], clickable: true },
        ]}
        highlightBids={["15"]}
      />,
    );
    expect(container.querySelectorAll(".stv-box")).toHaveLength(1);
    expect(container.querySelector(".stv-box--target")).toHaveAttribute("data-bid", "15");
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(container.querySelectorAll(".stv-box")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "1:1" }));
    expect(screen.getByText("100%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByText("125%")).toBeInTheDocument();
  });
});

describe("RunReplayPlayer", () => {
  const steps = [step0, step5] as StepDetail[];

  it("plays through steps and stops at the end", () => {
    vi.useFakeTimers();
    try {
      render(<RunReplayPlayer steps={steps} stepIntervalMs={1000} />);
      const slider = screen.getByRole("slider");
      fireEvent.click(screen.getByRole("button", { name: "Play" }));
      act(() => vi.advanceTimersByTime(1000));
      expect(slider).toHaveAttribute("aria-valuenow", "1");
      act(() => vi.advanceTimersByTime(5000));
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("follows new steps in live mode and resolves screenshot URLs", () => {
    const { rerender } = render(<RunReplayPlayer steps={[step0 as StepDetail]} apiBaseUrl="http://api/api/v1" />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "http://api/api/v1/runs/run_flight_search/steps/0/screenshot");
    rerender(<RunReplayPlayer steps={steps} apiBaseUrl="http://api/api/v1" />);
    expect(screen.getByRole("slider")).toHaveAttribute("aria-valuenow", "1");
  });

  it("lazily loads step detail", async () => {
    const { axtree_txt: _a, ...bare } = step5;
    const load = vi.fn(async () => step5 as StepDetail);
    render(<RunReplayPlayer steps={[bare as StepDetail]} getStepDetail={load} />);
    expect(await screen.findByText("'Search flights'")).toBeInTheDocument();
    expect(load).toHaveBeenCalledWith(5);
  });

  it("resets cached details when the run changes and stops loading on empty detail", async () => {
    const tree = (name: string) => ({ ...(step0 as StepDetail), axtree_txt: `RootWebArea '${name}'` });
    const runA = { ...flightRun, id: "run_a" };
    const runB = { ...flightRun, id: "run_b" };
    const base = { ...(step0 as StepDetail), axtree_txt: null } as StepDetail;
    const { rerender } = render(<RunReplayPlayer run={runA} steps={[base]} getStepDetail={() => tree("Run A")} />);
    expect(await screen.findByText("'Run A'")).toBeInTheDocument();
    rerender(<RunReplayPlayer run={runB} steps={[base]} getStepDetail={() => tree("Run B")} />);
    expect(await screen.findByText("'Run B'")).toBeInTheDocument();
    expect(screen.queryByText("'Run A'")).not.toBeInTheDocument();
    rerender(<RunReplayPlayer run={{ ...flightRun, id: "run_c" }} steps={[base]} getStepDetail={() => undefined} />);
    await act(async () => {});
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });

  it("retries a missing detail when the live step is updated", async () => {
    const base = { ...(step0 as StepDetail), axtree_txt: null } as StepDetail;
    let ready = false;
    const load = vi.fn(() => (ready ? { ...base, axtree_txt: "RootWebArea 'Ready'" } : undefined));
    const { rerender } = render(<RunReplayPlayer run={flightRun} steps={[base]} getStepDetail={load} />);
    await act(async () => {});
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
    ready = true;
    rerender(<RunReplayPlayer run={flightRun} steps={[{ ...base }]} getStepDetail={load} />);
    expect(await screen.findByText("'Ready'")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
