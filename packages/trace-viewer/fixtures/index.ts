/**
 * Fixtures recorded from a real BrowserGym episode (browsergym/openended, scripted agent),
 * regenerated with `python scripts/make_fixtures.py`. Shapes follow contracts/openapi.yaml.
 */
import type { ChatMessage, ElementBox, Run, StepDetail } from "../src/types";
import chatJson from "./flight-search/chat.json";
import runJson from "./flight-search/run.json";

const stepModules = import.meta.glob<StepDetail>("./flight-search/steps/*[0-9].json", { eager: true, import: "default" });
const boxModules = import.meta.glob<ElementBox[]>("./flight-search/steps/*.boxes.json", { eager: true, import: "default" });
const shotModules = import.meta.glob<string>("./flight-search/steps/*.png", { eager: true, import: "default", query: "?url" });

const indexOf = (path: string) => Number(/(\d+)(?:\.boxes)?\.(?:json|png)$/.exec(path)?.[1]);
const byIndex = <T,>(mods: Record<string, T>): T[] =>
  Object.entries(mods)
    .sort(([a], [b]) => indexOf(a) - indexOf(b))
    .map(([, v]) => v);

export const flightRun = runJson as Run;
export const flightChat = chatJson as ChatMessage[];
export const flightSteps: StepDetail[] = byIndex(stepModules);
export const flightBoxes: ElementBox[][] = byIndex(boxModules);
export const flightScreenshots: string[] = byIndex(shotModules);

export const failedRun: Run = {
  ...flightRun,
  id: "run_flight_search_failed",
  status: "failed",
  reward: 0,
  n_steps: 5,
  error: "TimeoutError: page.click: Timeout 5000ms exceeded waiting for selector [bid='29']",
  finished_at: flightSteps[4]?.timestamp ?? flightRun.finished_at,
};
export const failedSteps: StepDetail[] = flightSteps.slice(0, 5).map((s, i) => (i === 4 ? { ...s, terminated: true } : s));
export const failedChat: ChatMessage[] = [
  ...flightChat.slice(0, 3),
  {
    role: "infeasible",
    message: "I could not tick 'Direct flights only': the checkbox did not respond.",
    timestamp: flightSteps[4]?.timestamp ?? flightRun.created_at,
  },
];

export const sampleActions: string[] = [
  "click('a42')",
  "fill('b12', 'hello world')",
  "select_option('21', ['Business', 'First'])",
  "press('15', 'ControlOrMeta+a')",
  "drag_and_drop('31', '47')",
  "dblclick('7', button='left')",
  "hover('88')",
  "scroll(0, 200)",
  "mouse_click(412.5, 230)",
  "keyboard_type('Lisbon')",
  "goto('https://skyhop.example/flights?from=PAR')",
  "go_back()",
  "tab_focus(2)",
  "send_msg_to_user('Held SH 218 for €389.')",
  "report_infeasible('The site requires a login I do not have.')",
  "noop(1000)",
  "upload_file('19', '/tmp/passport.pdf')",
  "click('a42'",
];
