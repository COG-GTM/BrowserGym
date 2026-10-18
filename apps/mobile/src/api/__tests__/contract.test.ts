/**
 * Validates mock fixtures and simulated events against contracts/openapi.yaml so mock mode
 * stays contract-conformant.
 */
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { readFileSync } from 'fs';
import { join } from 'path';
import { parse } from 'yaml';

import { LIVE_RUN_ID, MockSideApi } from '../mock/mockApi';
import type { RunEvent } from '../types';
import { runBody } from '@/test/render';

const doc = parse(readFileSync(join(__dirname, '../../../../../contracts/openapi.yaml'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema({ $id: 'side', components: doc.components });

function expectValid(schema: string, value: unknown) {
  const validate = ajv.getSchema(`side#/components/schemas/${schema}`);
  if (!validate) throw new Error(`schema ${schema} missing from contract`);
  const ok = validate(value);
  if (!ok) throw new Error(`${schema} invalid: ${ajv.errorsText(validate.errors)}\n${JSON.stringify(value, null, 2)}`);
}

describe('mock fixtures conform to the OpenAPI contract', () => {
  const api = new MockSideApi({ latencyMs: 0, startDelayMs: 0, stepIntervalMs: 5 });
  afterAll(() => api.dispose());

  it('tasks and agents', async () => {
    for (const task of await api.listTasks()) expectValid('Task', task);
    for (const agent of await api.listAgents()) expectValid('AgentInfo', agent);
  });

  it('runs, steps, step detail and chat', async () => {
    const page = await api.listRuns();
    for (const run of page.items) {
      expectValid('Run', run);
      for (const step of await api.listSteps(run.id)) expectValid('Step', step);
      for (const msg of await api.listChat(run.id)) expectValid('ChatMessage', msg);
    }
    expectValid('StepDetail', await api.getStep(LIVE_RUN_ID, 0));
  });

  it('streamed RunEvents', async () => {
    const run = await api.createRun(runBody('browsergym/openended', { goal: 'Summarise example.com' }));
    expectValid('Run', run);
    const events = await new Promise<RunEvent[]>((resolve) => {
      const seen: RunEvent[] = [];
      api.subscribeRunEvents(run.id, { onEvent: (e) => seen.push(e), onClose: () => resolve(seen) });
    });
    expect(events.length).toBeGreaterThan(2);
    for (const event of events) expectValid('RunEvent', event);
  });
});
