import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect } from "@playwright/test";
import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";

export const CONTRACT_PATH = fileURLToPath(new URL("../../contracts/openapi.yaml", import.meta.url));

type Json = Record<string, any>;
export type Method = "get" | "post" | "put" | "patch" | "delete";
export const HTTP_METHODS: Method[] = ["get", "post", "put", "patch", "delete"];

export const contract: Json = parse(readFileSync(CONTRACT_PATH, "utf8"));

// OpenAPI 3.1 schemas are JSON Schema 2020-12 (+ a few annotation keywords).
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addFormat("binary", true);
ajv.addKeyword({ keyword: "example" });
ajv.addSchema(contract, "openapi.yaml");

const cache = new Map<string, ValidateFunction>();

const pointer = (...parts: (string | number)[]) =>
  parts.map((p) => String(p).replace(/~/g, "~0").replace(/\//g, "~1")).join("/");

function validatorFor(ref: string): ValidateFunction {
  const cached = cache.get(ref);
  if (cached) return cached;
  const fn = ajv.compile({ $ref: `openapi.yaml#/${ref}` });
  cache.set(ref, fn);
  return fn;
}

function deref(node: Json): Json {
  let cur = node;
  while (cur && typeof cur.$ref === "string") {
    cur = cur.$ref
      .replace(/^#\//, "")
      .split("/")
      .map((p: string) => p.replace(/~1/g, "/").replace(/~0/g, "~"))
      .reduce((acc: Json, key: string) => acc?.[key], contract);
  }
  return cur;
}

/** Every operation declared in the contract, e.g. `getRun -> GET /runs/{run_id}`. */
export function contractOperations() {
  const ops: { operationId: string; method: Method; path: string; statuses: string[] }[] = [];
  for (const [path, item] of Object.entries<Json>(contract.paths)) {
    for (const method of HTTP_METHODS) {
      const op = item[method];
      if (op) ops.push({ operationId: op.operationId, method, path, statuses: Object.keys(op.responses ?? {}) });
    }
  }
  return ops;
}

export function operation(operationId: string) {
  const op = contractOperations().find((o) => o.operationId === operationId);
  if (!op) throw new Error(`operationId ${operationId} is not in ${CONTRACT_PATH}`);
  return op;
}

/** JSON pointer (without leading `#/`) to a response schema in the contract, following `$ref` responses. */
function responseSchemaRef(path: string, method: Method, status: number | string, mediaType: string): string | null {
  const responses = contract.paths?.[path]?.[method]?.responses;
  if (!responses) throw new Error(`${method.toUpperCase()} ${path} is not in the contract`);
  const raw = responses[String(status)];
  if (!raw) throw new Error(`${method.toUpperCase()} ${path} does not declare status ${status}`);
  if (raw.$ref) {
    const target = raw.$ref.replace(/^#\//, "");
    return deref(raw).content?.[mediaType]?.schema ? `${target}/${pointer("content", mediaType, "schema")}` : null;
  }
  return raw.content?.[mediaType]?.schema ? pointer("paths", path, method, "responses", String(status), "content", mediaType, "schema") : null;
}

const formatErrors = (fn: ValidateFunction) =>
  ajv.errorsText(fn.errors, { separator: "\n  ", dataVar: "body" });

/** Asserts `body` matches the response schema declared for (path, method, status). */
export function expectResponseSchema(path: string, method: Method, status: number, body: unknown, mediaType = "application/json") {
  const ref = responseSchemaRef(path, method, status, mediaType);
  expect(ref, `${method.toUpperCase()} ${path} ${status} has a ${mediaType} schema`).not.toBeNull();
  const fn = validatorFor(ref!);
  const ok = fn(body);
  expect(ok, `response of ${method.toUpperCase()} ${path} ${status} violates the contract:\n  ${ok ? "" : formatErrors(fn)}\nbody: ${JSON.stringify(body).slice(0, 2000)}`).toBe(true);
}

/** Asserts `value` matches `#/components/schemas/<name>`. */
export function expectSchema(name: string, value: unknown, label = name) {
  const fn = validatorFor(pointer("components", "schemas", name));
  const ok = fn(value);
  expect(ok, `${label} violates components.schemas.${name}:\n  ${ok ? "" : formatErrors(fn)}\nvalue: ${JSON.stringify(value).slice(0, 2000)}`).toBe(true);
}

/** Returns the enum of a component schema, e.g. schemaEnum("RunStatus"). */
export function schemaEnum(name: string): string[] {
  return deref(contract.components.schemas[name]).enum;
}
