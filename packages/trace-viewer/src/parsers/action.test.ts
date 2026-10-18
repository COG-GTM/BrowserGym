import { describe, expect, it } from "vitest";
import { ActionParseError, parseAction, parseActions, tryParseAction, tryParseActions } from "./action";

describe("parseAction", () => {
  it("parses click with a bid", () => {
    const a = parseAction("click('a42')");
    expect(a).toMatchObject({ name: "click", args: ["a42"], category: "element", bid: "a42", bids: ["a42"], text: null });
  });

  it("parses fill with value text", () => {
    const a = parseAction("fill('b12', 'text')");
    expect(a.bid).toBe("b12");
    expect(a.text).toBe("text");
    expect(a.args).toEqual(["b12", "text"]);
  });

  it("handles double quotes, escapes and unicode", () => {
    const a = parseAction(`fill("7", "It's \\"quoted\\"\\nnext — ok")`);
    expect(a.text).toBe(`It's "quoted"\nnext — ok`);
    expect(parseAction("send_msg_to_user('it\\'s done')").text).toBe("it's done");
  });

  it("parses keyword args, booleans, None and lists", () => {
    const a = parseAction("click('12', button='right', modifiers=['Shift', 'ControlOrMeta'])");
    expect(a.kwargs).toEqual({ button: "right", modifiers: ["Shift", "ControlOrMeta"] });
    expect(parseAction("fill('3', 'x', enable_autocomplete_menu=True)").kwargs).toEqual({ enable_autocomplete_menu: true });
    expect(parseAction("select_option('21', ['A', 'B'])").text).toBe("A, B");
    expect(parseAction("foo(None, False, (1, 2))").args).toEqual([null, false, [1, 2]]);
  });

  it("extracts both bids for drag_and_drop", () => {
    expect(parseAction("drag_and_drop('31', '47')").bids).toEqual(["31", "47"]);
    expect(parseAction("drag_and_drop(to_bid='9', from_bid='8')").bids).toEqual(["8", "9"]);
  });

  it("categorises coordinate, keyboard, nav, tab, message and wait actions", () => {
    expect(parseAction("scroll(0, -200.5)")).toMatchObject({ category: "mouse", args: [0, -200.5], bid: null, text: "0, -200.5" });
    expect(parseAction("mouse_click(412.5, 230)").category).toBe("mouse");
    expect(parseAction("keyboard_press('Enter')")).toMatchObject({ category: "keyboard", text: "Enter" });
    expect(parseAction("goto('https://a.b/c?d=1')")).toMatchObject({ category: "navigation", text: "https://a.b/c?d=1" });
    expect(parseAction("go_back()")).toMatchObject({ category: "navigation", args: [] });
    expect(parseAction("tab_focus(2)")).toMatchObject({ category: "tab", text: "2" });
    expect(parseAction("report_infeasible('nope')")).toMatchObject({ category: "message", text: "nope" });
    expect(parseAction("noop(1000)")).toMatchObject({ category: "wait", text: "1000 ms" });
    expect(parseAction("noop()").text).toBeNull();
  });

  it("accepts numeric bids and unknown actions", () => {
    expect(parseAction("click(42)").bid).toBe("42");
    expect(parseAction("custom_tool('x')")).toMatchObject({ name: "custom_tool", category: "unknown", bids: [] });
  });

  it("tolerates whitespace and trailing commas", () => {
    expect(parseAction("  click( 'a1' , )  ").bid).toBe("a1");
  });

  it("throws ActionParseError on malformed input", () => {
    expect(() => parseAction("click('a42'")).toThrow(ActionParseError);
    expect(() => parseAction("click(a42)")).toThrow(ActionParseError);
    expect(() => parseAction("fill('1', 'unterminated)")).toThrow(/Unterminated/);
    expect(() => parseAction("click(button='left', 'a1')")).toThrow(/Positional/);
    expect(() => parseAction("")).toThrow(/Empty/);
  });

  it("tryParseAction returns null instead of throwing", () => {
    expect(tryParseAction("nope(")).toBeNull();
    expect(tryParseAction(null)).toBeNull();
    expect(tryParseAction("hover('5')")?.bid).toBe("5");
  });
});

describe("parseActions", () => {
  it("parses multi-action strings with comments", () => {
    const all = parseActions("# fill the form\nfill('1', 'a # not a comment')\nclick('2')  # submit\n");
    expect(all.map((a) => a.name)).toEqual(["fill", "click"]);
    expect(all[0]!.text).toBe("a # not a comment");
    expect(parseActions("click('1'); click('2')")).toHaveLength(2);
  });
});

describe("comments and multi-line strings", () => {
  it("keeps # inside triple-quoted strings across lines", () => {
    const a = parseAction("fill('1', '''first\n#second\nthird''')  # trailing comment");
    expect(a.text).toBe("first\n#second\nthird");
  });

  it("tryParseActions returns every call", () => {
    expect(tryParseActions("fill('1','Paris'); click('2')")?.map((a) => a.bid)).toEqual(["1", "2"]);
    expect(tryParseActions("")).toBeNull();
    expect(tryParseActions("click(")).toBeNull();
  });
});
