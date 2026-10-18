import type { AgentInfo, Task } from '../types';

export const MOCK_TASKS: Task[] = [
  {
    id: 'browsergym/openended',
    benchmark: 'openended',
    title: 'Open-ended task',
    description: 'Give the agent any goal and start URL.',
    requires_setup: false,
  },
  {
    id: 'browsergym/miniwob.click-test',
    benchmark: 'miniwob',
    title: 'Click test',
    description: 'Click the button labelled “Submit”.',
    requires_setup: false,
  },
  {
    id: 'browsergym/miniwob.click-button',
    benchmark: 'miniwob',
    title: 'Click button',
    description: 'Click on a specific button in a generated form.',
    requires_setup: false,
  },
  {
    id: 'browsergym/miniwob.click-button-sequence',
    benchmark: 'miniwob',
    title: 'Click button sequence',
    description: 'Click button ONE, then click button TWO.',
    requires_setup: false,
  },
  {
    id: 'browsergym/miniwob.login-user',
    benchmark: 'miniwob',
    title: 'Login user',
    description: 'Enter the username and password, then press login.',
    requires_setup: false,
  },
  {
    id: 'browsergym/miniwob.book-flight',
    benchmark: 'miniwob',
    title: 'Book flight',
    description: 'Book the shortest one-way flight from the given city.',
    requires_setup: false,
  },
  {
    id: 'browsergym/miniwob.enter-date',
    benchmark: 'miniwob',
    title: 'Enter date',
    description: 'Enter a date into the text field and submit.',
    requires_setup: false,
  },
  {
    id: 'browsergym/webarena.310',
    benchmark: 'webarena',
    title: 'WebArena #310',
    description: 'Shopping admin: report the top-1 best selling product in 2022.',
    requires_setup: true,
  },
  {
    id: 'browsergym/visualwebarena.12',
    benchmark: 'visualwebarena',
    title: 'VisualWebArena #12',
    description: 'Classifieds: find the listing that matches the image.',
    requires_setup: true,
  },
  {
    id: 'browsergym/workarena.servicenow.order-ipad-pro',
    benchmark: 'workarena',
    title: 'Order an iPad Pro',
    description: 'ServiceNow service catalog: order an iPad Pro with the given configuration.',
    requires_setup: true,
  },
];

export const MOCK_AGENTS: AgentInfo[] = [
  { type: 'mock', title: 'Mock (offline, deterministic)', models: [] },
  { type: 'scripted', title: 'Scripted (replay actions)', models: [] },
  { type: 'openai', title: 'OpenAI', models: ['gpt-4o', 'gpt-4o-mini', 'o4-mini'] },
  { type: 'anthropic', title: 'Anthropic', models: ['claude-sonnet-4-5', 'claude-haiku-4-5'] },
];

export const MOCK_SCREENSHOTS = {
  'step-0': require('../../../assets/mock/step-0.png'),
  'step-1': require('../../../assets/mock/step-1.png'),
  'step-2': require('../../../assets/mock/step-2.png'),
  'step-3': require('../../../assets/mock/step-3.png'),
  'step-4': require('../../../assets/mock/step-4.png'),
  'openended-0': require('../../../assets/mock/openended-0.png'),
  'openended-1': require('../../../assets/mock/openended-1.png'),
} as const;

export type MockScreenshotKey = keyof typeof MOCK_SCREENSHOTS;

/** One scripted agent step: what the simulated agent "does" and what it says. */
export interface ScriptStep {
  action: string | null;
  thought: string;
  url: string;
  screenshot: MockScreenshotKey | null;
  reward?: number;
  terminated?: boolean;
  chat?: string;
  error?: string;
}

const CLICK_TEST_URL = 'http://localhost:8000/miniwob/click-test.html';

export const CLICK_TEST_SCRIPT: ScriptStep[] = [
  {
    action: null,
    thought: 'Episode reset. Reading the goal: click the button labelled “Submit”.',
    url: CLICK_TEST_URL,
    screenshot: 'step-0',
  },
  {
    action: "fill('a12', 'Ada Lovelace')",
    thought: 'The form has a required Name field (bid a12). Filling it before submitting.',
    url: CLICK_TEST_URL,
    screenshot: 'step-1',
  },
  {
    action: "fill('a17', 'ada@side.dev')",
    thought: 'Name is filled. The Email field (bid a17) is also required.',
    url: CLICK_TEST_URL,
    screenshot: 'step-2',
  },
  {
    action: 'scroll(0, 120)',
    thought: 'Scrolling so the Submit button (bid a31) is fully in view.',
    url: CLICK_TEST_URL,
    screenshot: 'step-3',
  },
  {
    action: "click('a31')",
    thought: 'Submit is visible and enabled. Clicking it should complete the task.',
    url: CLICK_TEST_URL,
    screenshot: 'step-4',
    reward: 1,
    terminated: true,
    chat: 'Done — I filled the form and clicked “Submit”. The task reported reward 1.0.',
  },
];

export function openendedScript(goal: string, startUrl: string): ScriptStep[] {
  return [
    {
      action: `goto('${startUrl}')`,
      thought: `Starting at ${startUrl} to work on: ${goal}`,
      url: startUrl,
      screenshot: 'openended-0',
    },
    {
      action: 'scroll(0, 300)',
      thought: 'Skimming the page for anything relevant to the goal.',
      url: startUrl,
      screenshot: 'openended-0',
    },
    {
      action: "click('a5')",
      thought: 'The “More information…” link (bid a5) looks like the best lead.',
      url: startUrl,
      screenshot: 'openended-1',
    },
    {
      action: "send_msg_to_user('I reviewed the page and summarised it for you.')",
      thought: 'I have enough information to answer.',
      url: startUrl,
      screenshot: 'openended-1',
      terminated: true,
      chat: 'I reviewed the page and summarised it for you.',
    },
  ];
}

type Action = [action: string, thought: string];

/** Screenshot-less replay for a MiniWoB task: one reset step, then the given actions; the last one earns reward 1. */
function miniwobScript(page: string, actions: Action[], done: string): ScriptStep[] {
  const url = `http://localhost:8000/miniwob/${page}.html`;
  return [
    { action: null, thought: 'Episode reset. Reading the goal and the accessibility tree.', url, screenshot: null },
    ...actions.map(([action, thought], i): ScriptStep => {
      const last = i === actions.length - 1;
      return { action, thought, url, screenshot: null, ...(last ? { reward: 1, terminated: true, chat: done } : {}) };
    }),
  ];
}

const TASK_SCRIPTS: Record<string, ScriptStep[]> = {
  'browsergym/miniwob.click-test': CLICK_TEST_SCRIPT,
  'browsergym/miniwob.click-button': miniwobScript(
    'click-button',
    [["click('b7')", 'The goal names one button; bid b7 matches its label. Clicking it.']],
    'Clicked the requested button. Reward 1.0.',
  ),
  'browsergym/miniwob.click-button-sequence': miniwobScript(
    'click-button-sequence',
    [
      ["click('b3')", 'Button ONE is bid b3; it has to be clicked first.'],
      ["click('b4')", 'Now button TWO (bid b4) to finish the sequence.'],
    ],
    'Clicked ONE, then TWO. Reward 1.0.',
  ),
  'browsergym/miniwob.login-user': miniwobScript(
    'login-user',
    [
      ["fill('u5', 'kanesha')", 'The username textbox is bid u5; typing the requested username.'],
      ["fill('p6', 'qL3x9')", 'Password textbox is bid p6; typing the requested password.'],
      ["click('l9')", 'Both fields are filled. Clicking Login (bid l9).'],
    ],
    'Logged in with the requested credentials. Reward 1.0.',
  ),
  'browsergym/miniwob.book-flight': miniwobScript(
    'book-flight',
    [
      ["fill('f2', 'Anchorage')", 'Typing the departure city into From (bid f2).'],
      ["fill('t3', 'Denver')", 'Typing the destination into To (bid t3).'],
      ["click('s8')", 'Searching for flights (bid s8).'],
      ["click('r14')", 'Result r14 is the shortest one-way flight. Booking it.'],
    ],
    'Booked the shortest one-way flight. Reward 1.0.',
  ),
  'browsergym/miniwob.enter-date': miniwobScript(
    'enter-date',
    [
      ["fill('d4', '03/14/2026')", 'The date textbox is bid d4; entering the requested date.'],
      ["click('s5')", 'Submitting the form (bid s5).'],
    ],
    'Entered the date and submitted. Reward 1.0.',
  ),
};

/** The mock replay for a task, or null when there is no offline replay for it. */
export function taskScript(taskId: string, goal: string, startUrl: string): ScriptStep[] | null {
  if (taskId === 'browsergym/openended') return openendedScript(goal, startUrl);
  return TASK_SCRIPTS[taskId] ?? null;
}
