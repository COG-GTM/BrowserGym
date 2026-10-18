import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Step } from "../types";
import { StepTimeline } from "./StepTimeline";

const mk = (index: number, action: string | null, err: string | null = null): Step => ({
  index,
  action,
  reward: 0,
  terminated: action === null,
  truncated: false,
  last_action_error: err,
  timestamp: `2026-10-18T02:40:${String(index).padStart(2, "0")}Z`,
});

const steps: Step[] = [
  mk(0, "fill('15', 'Paris')"),
  mk(1, "click('zz99')"),
  mk(2, "click('29')", 'ValueError: Could not find element with bid "zz99"'),
  ...Array.from({ length: 9 }, (_, i) => mk(i + 3, "scroll(0, 100)")),
  mk(12, null),
];

function Harness({ initial = 0, onChange }: { initial?: number; onChange?: (i: number) => void }) {
  const [i, setI] = useState(initial);
  return (
    <StepTimeline
      steps={steps}
      currentIndex={i}
      onChange={(n) => {
        setI(n);
        onChange?.(n);
      }}
    />
  );
}

describe("StepTimeline keyboard navigation", () => {
  it("exposes slider semantics", () => {
    render(<Harness initial={2} />);
    const slider = screen.getByRole("slider", { name: "Step" });
    expect(slider).toHaveAttribute("aria-valuemin", "0");
    expect(slider).toHaveAttribute("aria-valuemax", "12");
    expect(slider).toHaveAttribute("aria-valuenow", "2");
    expect(slider).toHaveAttribute("aria-valuetext", "Step 3 of 13: click");
  });

  it("moves with arrows, PageUp/PageDown, Home/End and clamps at the ends", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const slider = screen.getByRole("slider");
    slider.focus();

    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(slider).toHaveAttribute("aria-valuenow", "2");
    await user.keyboard("{ArrowLeft}");
    expect(slider).toHaveAttribute("aria-valuenow", "1");
    await user.keyboard("{PageUp}");
    expect(slider).toHaveAttribute("aria-valuenow", "6");
    await user.keyboard("{ArrowUp}");
    expect(slider).toHaveAttribute("aria-valuenow", "7");
    await user.keyboard("{PageDown}");
    expect(slider).toHaveAttribute("aria-valuenow", "2");
    await user.keyboard("{End}");
    expect(slider).toHaveAttribute("aria-valuenow", "12");
    await user.keyboard("{ArrowRight}");
    expect(slider).toHaveAttribute("aria-valuenow", "12");
    await user.keyboard("{Home}");
    expect(slider).toHaveAttribute("aria-valuenow", "0");
    onChange.mockClear();
    await user.keyboard("{ArrowLeft}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows the current step label and marks failed actions", () => {
    render(<Harness initial={1} />);
    expect(screen.getByText("2", { selector: "strong" })).toBeInTheDocument();
    // step 1's action error is reported on step 2
    expect(screen.getByTestId("step-marker-1")).toHaveClass("stv-timeline__marker--error");
    expect(screen.getByTestId("step-marker-0")).not.toHaveClass("stv-timeline__marker--error");
    expect(screen.getByTestId("step-marker-12")).toHaveClass("stv-timeline__marker--terminal");
  });

  it("scrubs with the pointer", () => {
    render(<Harness />);
    const slider = screen.getByRole("slider");
    slider.getBoundingClientRect = () => ({ left: 0, width: 240, top: 0, height: 28, right: 240, bottom: 28, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.pointerDown(slider, { clientX: 120, pointerId: 1 });
    expect(slider).toHaveAttribute("aria-valuenow", "6");
    fireEvent.pointerMove(slider, { clientX: 240, pointerId: 1 });
    expect(slider).toHaveAttribute("aria-valuenow", "12");
    fireEvent.pointerUp(slider, { pointerId: 1 });
    fireEvent.pointerMove(slider, { clientX: 0, pointerId: 1 });
    expect(slider).toHaveAttribute("aria-valuenow", "12");
  });
});
