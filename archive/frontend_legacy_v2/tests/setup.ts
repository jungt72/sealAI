import React from "react";
import { vi } from "vitest";

const styleStub = () => null;

vi.mock("styled-jsx/style", () => ({
  __esModule: true,
  default: styleStub,
  Style: styleStub,
}));
vi.mock("styled-jsx/style.js", () => ({
  __esModule: true,
  default: styleStub,
  Style: styleStub,
}));
vi.mock("styled-jsx/css", () => ({ __esModule: true, default: () => ({}) }));

const jsxWarning = /Received `true` for a non-boolean attribute `jsx`/;
const originalError = console.error.bind(console);
const originalWarn = console.warn.bind(console);

const shouldSuppress = (args: unknown[]) => {
  const message = args.map((arg) => (typeof arg === "string" ? arg : String(arg))).join(" ");
  return jsxWarning.test(message);
};

console.error = (...args) => {
  if (shouldSuppress(args)) return;
  originalError(...args);
};

console.warn = (...args) => {
  if (shouldSuppress(args)) return;
  originalWarn(...args);
};

const originalStderrWrite = process.stderr.write.bind(process.stderr);
process.stderr.write = ((chunk: unknown, ...args: unknown[]) => {
  const text = typeof chunk === "string" ? chunk : Buffer.from(chunk as any).toString();
  if (text.includes("Received `true` for a non-boolean attribute `jsx`")) {
    return true;
  }
  return originalStderrWrite(chunk as any, ...(args as any));
}) as typeof process.stderr.write;

const originalCreateElement = React.createElement;
React.createElement = ((type: any, props: any, ...children: any[]) => {
  if (type === "style" && props && "jsx" in props) {
    const rest = { ...(props as Record<string, unknown>) };
    delete (rest as Record<string, unknown>).jsx;
    return originalCreateElement(type, rest, ...children);
  }
  return originalCreateElement(type, props, ...children);
}) as typeof React.createElement;

vi.mock("react/jsx-runtime", async () => {
  const actual = await vi.importActual<typeof import("react/jsx-runtime")>("react/jsx-runtime");
  const stripJsxProp = (type: unknown, props: any) => {
    if (type === "style" && props && "jsx" in props) {
      const rest = { ...props };
      delete rest.jsx;
      return rest;
    }
    return props;
  };
  return {
    ...actual,
    jsx: (type: any, props: any, key?: any) => actual.jsx(type, stripJsxProp(type, props), key),
    jsxs: (type: any, props: any, key?: any) => actual.jsxs(type, stripJsxProp(type, props), key),
  };
});

vi.mock("react/jsx-dev-runtime", async () => {
  const actual = await vi.importActual<typeof import("react/jsx-dev-runtime")>("react/jsx-dev-runtime");
  const stripJsxProp = (type: unknown, props: any) => {
    if (type === "style" && props && "jsx" in props) {
      const rest = { ...props };
      delete rest.jsx;
      return rest;
    }
    return props;
  };
  return {
    ...actual,
    jsxDEV: (type: any, props: any, key?: any, isStatic?: any, source?: any, self?: any) =>
      actual.jsxDEV(type, stripJsxProp(type, props), key, isStatic, source, self),
  };
});
