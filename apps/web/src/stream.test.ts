import assert from "node:assert/strict";
import test from "node:test";
import { briefFromDone, emptyView, parseSSE, reduce } from "./stream.js";

test("tokens paint, then done replaces the bubble", () => {
  let view = emptyView();
  view = reduce(view, { event: "token", text: "Email " });
  view = reduce(view, { event: "token", text: "avery@example.com" });
  assert.equal(view.draft, "Email avery@example.com");
  assert.equal(view.committed, null);
  view = reduce(view, {
    event: "done",
    messageId: "m1",
    text: "Email [redacted-email]",
  });
  assert.equal(view.draft, "Email [redacted-email]");
  assert.equal(view.committed, "Email [redacted-email]");
  assert.equal(view.streaming, false);
});

test("a done event with a brief can confirm, and a reply without one cannot", () => {
  const offered = parseSSE(
    'event: done\ndata: {"messageId":"m1","text":"Confirm","brief":{"role":"barista","location":"Fitzroy","hours":"weekends, part-time","pay":"about $32 an hour"}}\n\n',
  );
  const question = parseSSE('event: done\ndata: {"messageId":"m2","text":"A question does not start a hire."}\n\n');
  const brief = briefFromDone(offered.events[0]);
  assert.ok(brief);
  assert.equal(brief.role, "barista");
  assert.equal(briefFromDone(question.events[0]), null);
});

test("parser keeps a partial block and drops a function call", () => {
  const first = parseSSE("event: token\ndata: {\"text\":\"Hi\"}\n\nevent: token\ndata: {\"functionCall\":{}}\n\nevent: do");
  assert.deepEqual(first.events, [{ event: "token", text: "Hi" }]);
  assert.equal(first.rest, "event: do");
  const second = parseSSE(first.rest + "ne\ndata: {\"messageId\":\"m1\",\"text\":\"Hi\"}\n\n");
  assert.deepEqual(second.events, [{ event: "done", messageId: "m1", text: "Hi" }]);
});
