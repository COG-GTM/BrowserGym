import { describe, expect, it } from "vitest";
import step5 from "../../fixtures/flight-search/steps/5.json";
import { ancestorsOf, nodeMatches, parseAXTree, parseAXTreeLine } from "./axtree";

describe("parseAXTreeLine", () => {
  it("parses bid, role, name, value and props", () => {
    const n = parseAXTreeLine("\t\t[15] textbox 'From' value='Paris', focused, required", 3)!;
    expect(n).toMatchObject({ bid: "15", role: "textbox", name: "From", value: "Paris", depth: 2, line: 3 });
    expect(n.props).toEqual({ focused: true, required: true });
  });

  it("parses nodes without bid or name", () => {
    expect(parseAXTreeLine("RootWebArea 'Skyhop — Book a flight', focused")).toMatchObject({ bid: null, role: "RootWebArea", depth: 0, props: { focused: true } });
    expect(parseAXTreeLine("\t[6] banner ''")).toMatchObject({ bid: "6", name: "" });
    expect(parseAXTreeLine("\t\tgeneric")).toMatchObject({ bid: null, role: "generic", name: "" });
  });

  it("handles repr-style double-quoted names and quoted commas in props", () => {
    const n = parseAXTreeLine(`\t[9] link "Joe's page, home", url='https://x.y/?a=1, b'`)!;
    expect(n.name).toBe("Joe's page, home");
    expect(n.props.url).toBe("https://x.y/?a=1, b");
  });

  it("keeps numeric props and expanded=False", () => {
    const n = parseAXTreeLine("[26] spinbutton 'Passengers' value=1, valuemin=1, expanded=False")!;
    expect(n.value).toBe("1");
    expect(n.props).toEqual({ valuemin: "1", expanded: "False" });
  });

  it("ignores blank lines", () => {
    expect(parseAXTreeLine("   ")).toBeNull();
  });
});

describe("parseAXTree", () => {
  const tree = parseAXTree(step5.axtree_txt);

  it("builds the hierarchy from a real BrowserGym axtree", () => {
    expect(tree.roots).toHaveLength(1);
    expect(tree.roots[0]!.role).toBe("RootWebArea");
    const button = tree.byBid.get("30")![0]!;
    expect(button).toMatchObject({ role: "button", name: "Search flights" });
    expect(ancestorsOf(button).map((a) => a.role)).toEqual(["Section", "main", "RootWebArea"]);
    const textbox = tree.byBid.get("15")![0]!;
    expect(textbox.children[0]).toMatchObject({ role: "StaticText", name: "Paris" });
  });

  it("indexes repeated bids", () => {
    expect(tree.byBid.get("19")!.map((n) => n.role)).toEqual(["Date", "spinbutton", "spinbutton", "spinbutton"]);
  });

  it("returns an empty tree for null input", () => {
    expect(parseAXTree(null).nodes).toEqual([]);
  });
});

describe("nodeMatches", () => {
  const n = parseAXTreeLine("[21] combobox 'Cabin' value='Business'")!;
  const node = { ...n, children: [], parent: null };
  it("matches role, name, value, bid and [bid]", () => {
    expect(nodeMatches(node, "combo")).toBe(true);
    expect(nodeMatches(node, "CABIN")).toBe(true);
    expect(nodeMatches(node, "business")).toBe(true);
    expect(nodeMatches(node, "21")).toBe(true);
    expect(nodeMatches(node, "[21]")).toBe(true);
    expect(nodeMatches(node, "[2]")).toBe(false);
    expect(nodeMatches(node, " ")).toBe(false);
  });
});
