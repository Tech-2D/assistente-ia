const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");

test("new chat and page exit discard sessions and ignore late answers", async () => {
  const handlers = new Map();
  const windowHandlers = new Map();
  const elements = new Map();
  const calls = [];
  const pending = [];
  let nextId = 0;

  function element(selector) {
    if (!elements.has(selector)) {
      elements.set(selector, {
        children: [], value: "", disabled: false, textContent: "",
        classList: { toggle() {} },
        addEventListener(name, fn) { handlers.set(`${selector}:${name}`, fn); },
        append(...children) { this.children.push(...children); },
        replaceChildren(...children) { this.children = children; },
        remove() {}, focus() {}, add() {},
      });
    }
    return elements.get(selector);
  }

  const user = { uid: "user", email: "test@example.test", getIdToken: async () => "token" };
  const sandbox = {
    document: {
      querySelector: element,
      createElement: () => element(`created-${++nextId}`),
      createTextNode: (text) => ({ textContent: text }),
    },
    window: { addEventListener(name, fn) { windowHandlers.set(name, fn); } },
    localStorage: { getItem: () => null },
    crypto: { randomUUID: () => `session-${++nextId}` },
    Option: function Option(label, value) { this.label = label; this.value = value; },
    AbortController, URL, console,
    initializeApp: () => ({}), getAuth: () => ({}), setPersistence: async () => {},
    browserSessionPersistence: {}, onAuthStateChanged: (_auth, fn) => { void fn(user); },
    signInWithEmailAndPassword: async () => {}, signOut: async () => {},
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      if (url === "/api/config") return { ok: true, json: async () => ({ firebase: { apiKey: "x", appId: "x", projectId: "x" } }) };
      if (url === "/api/classes") return { ok: true, json: async () => ({ classes: [] }) };
      if (url === "/api/chat") return new Promise((resolve) => pending.push(resolve));
      return { ok: true, json: async () => ({ closed: true }) };
    },
  };
  let source = fs.readFileSync("static/app.js", "utf8");
  source = source.replace(/^import[\s\S]*?from "https:\/\/www\.gstatic\.com\/firebasejs\/12\.19\.0\/firebase-auth\.js";\s*/, "");
  vm.runInNewContext(source, sandbox);
  const tick = () => new Promise((resolve) => setImmediate(resolve));
  await tick();

  element("#message").value = "Quais provas?";
  const first = handlers.get("#chatForm:submit")({ preventDefault() {} });
  await tick();
  const firstRequest = calls.find((call) => call.url === "/api/chat");
  const firstId = JSON.parse(firstRequest.options.body).session_id;
  handlers.get("#newChat:click")();
  const deletedFirst = calls.find((call) => call.url === `/api/session/${firstId}`);
  assert.equal(deletedFirst.options.keepalive, true);
  assert.equal(deletedFirst.options.headers.Authorization, "Bearer token");
  assert.equal(firstRequest.options.signal.aborted, true);
  pending.shift()({ ok: true, json: async () => ({ session_id: firstId, answer: "resposta antiga", cards: [] }) });
  await first;
  assert.ok(!element("#messages").children.some((child) => child.textContent === "resposta antiga"));

  element("#message").value = "Quais tarefas?";
  const second = handlers.get("#chatForm:submit")({ preventDefault() {} });
  await tick();
  const secondRequest = calls.filter((call) => call.url === "/api/chat")[1];
  const secondId = JSON.parse(secondRequest.options.body).session_id;
  assert.notEqual(firstId, secondId);
  windowHandlers.get("pagehide")();
  assert.ok(calls.some((call) => call.url === `/api/session/${secondId}` && call.options.keepalive));
  assert.equal(secondRequest.options.signal.aborted, true);
  pending.shift()({ ok: true, json: async () => ({ session_id: secondId, answer: "resposta tardia", cards: [] }) });
  await second;
  assert.ok(!element("#messages").children.some((child) => child.textContent === "resposta tardia"));
});
