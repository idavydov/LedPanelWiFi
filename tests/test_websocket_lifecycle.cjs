// Run: node tests/test_websocket_lifecycle.cjs. Real service/RxJS, fake sockets and time.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('../web/node_modules/typescript');
const rx = require('../web/node_modules/rxjs');
const operators = require('../web/node_modules/rxjs/operators');

function service() {
  const clock = {now: 0}, sockets = [], timers = new Map();
  const redirects = [];
  const http = {result: rx.EMPTY, get: () => http.result};
  const heartbeat = new rx.Subject();
  let timerId = 0;
  class Socket extends rx.Subject {
    constructor(config) { super(); this.config = config; this.sent = []; sockets.push(this); }
    next(message) { this.sent.push(message); }
    open() { this.config.openObserver.next({}); }
    message(message) { rx.Subject.prototype.next.call(this, message); }
    fail() {
      rx.Subject.prototype.error.call(this, new Error('test transport failure'));
      this.config.closeObserver.next({code: 1006, reason: ''});
    }
    complete() {
      rx.Subject.prototype.complete.call(this);
      this.config.closeObserver.next({code: 1000, reason: ''});
    }
  }
  class Base {
    constructor() { this.destroy$ = new rx.Subject(); }
    ngOnDestroy() { this.destroy$.next(); this.destroy$.complete(); }
  }
  const context = {
    exports: {}, Date: {now: () => clock.now}, console,
    window: {location: {hostname: 'panel.local', assign: path => redirects.push(path)}}, document: {body: {classList: {toggle() {}}}},
    setTimeout(fn, delay) { const id = ++timerId; timers.set(id, {fn, delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
    require(name) {
      if (name === '@angular/core') return {Injectable: () => klass => klass};
      if (name === '@angular/common/http') return {};
      if (name === 'rxjs') return {...rx, interval: () => heartbeat};
      if (name === 'rxjs/operators') return operators;
      if (name === 'rxjs/webSocket') return {WebSocketSubject: Socket};
      if (name.endsWith('base.class')) return {Base};
      if (name.endsWith('/environment')) return {environment: {production: true}};
      throw new Error(name);
    },
  };
  const source = fs.readFileSync('web/src/app/services/websocket/websocket.service.ts', 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, experimentalDecorators: true
  }}).outputText, context);
  const controller = new context.exports.WebsocketService(http);
  function retry() {
    assert.equal(timers.size, 1);
    const [id, {fn, delay}] = timers.entries().next().value;
    assert.equal(delay, 5000); timers.delete(id); fn();
  }
  return {controller, clock, sockets, timers, heartbeat, retry, http, redirects};
}

test('expired browser sessions return to login while network failures keep reconnecting', () => {
  const {sockets, http, redirects, retry} = service();
  http.result = rx.throwError(() => ({status: 0}));
  sockets[0].fail(); assert.deepEqual(redirects, []); retry();
  http.result = rx.throwError(() => ({status: 404}));
  sockets[1].fail(); assert.deepEqual(redirects, []); retry();
  http.result = rx.throwError(() => ({status: 401}));
  sockets[2].fail(); assert.deepEqual(redirects, ['/login']);
});

test('failed handshake retries once and ignores late close events from old sockets', () => {
  const {controller, sockets, timers, retry} = service();
  let received = 0;
  controller.on('ir').subscribe(() => ++received);
  const first = sockets[0]; first.fail();
  assert.equal(timers.size, 1);
  first.config.closeObserver.next({code: 1006, reason: ''});
  assert.equal(timers.size, 1);
  retry(); const second = sockets[1]; second.open();
  second.message({e: 'ir', d: '{}'});
  assert.equal(received, 1); // listeners survive reconnecting
  assert.equal(controller.isConnected, true);
  first.config.closeObserver.next({code: 1006, reason: 'late old connection'});
  assert.equal(controller.isConnected, true);
  assert.equal(timers.size, 0);
  controller.ngOnDestroy();
});

test('any server traffic keeps heartbeat alive, including IR frames', () => {
  const {controller, clock, sockets, heartbeat, timers} = service();
  sockets[0].open();
  clock.now = 30000; heartbeat.next(0);
  clock.now = 45000; sockets[0].message({e: 'ir', d: '{}'});
  clock.now = 60000; heartbeat.next(1);
  clock.now = 90000; heartbeat.next(2);
  assert.equal(controller.isConnected, true);
  clock.now = 120000; heartbeat.next(3);
  assert.equal(controller.isConnected, false);
  assert.equal(timers.size, 1);
  assert.match(controller.lastClose.reason, /heartbeat timeout/);
  controller.ngOnDestroy();
});

test('resuming a suspended browser probes before declaring connection lost', () => {
  const {controller, clock, sockets, heartbeat, timers} = service();
  sockets[0].open();
  clock.now = 300000; heartbeat.next(0);
  assert.equal(controller.isConnected, true);
  assert.equal(timers.size, 0);
  assert.equal(sockets[0].sent.length, 2); // initial probe plus resume probe
  sockets[0].message({e: 'stt', d: '{}'});
  clock.now += 30000; heartbeat.next(1);
  assert.equal(controller.isConnected, true);
  controller.ngOnDestroy();
});

test('destroy cancels queued reconnect and removes heartbeat subscription', () => {
  const {controller, sockets, timers, heartbeat} = service();
  sockets[0].fail(); assert.equal(timers.size, 1);
  controller.ngOnDestroy();
  assert.equal(timers.size, 0);
  heartbeat.next(1);
  assert.equal(sockets.length, 1);
});

test('loading text files limits HTTP concurrency and continues after a failed request', () => {
  const source = fs.readFileSync('web/src/app/services/management/management.service.ts', 'utf8');
  const start = source.indexOf('  public loadTextLines()');
  const method = source.slice(start, source.lastIndexOf('\n}'));
  let active = 0, peak = 0;
  const requests = [];
  const httpClient = {get(path) {
    return new rx.Observable(observer => {
      ++active; peak = Math.max(peak, active); requests.push({path, observer});
      return () => --active;
    });
  }};
  class Headers { set() { return this; } }
  const context = {...rx, HttpHeaders: Headers, Date, httpClient,
    isNullOrUndefinedOrEmpty: value => value == null || value === '', result: null};
  const script = `class Loader { text_lines=[]; destroy$=new Subject(); httpClient=httpClient; ${method} }
    result=new Loader(); result.loadTextLines();`;
  vm.runInNewContext(ts.transpileModule(script, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText, context);
  assert.equal(requests.length, 2);
  for (let i = 0; i < 36; i++) {
    assert.ok(requests[i]);
    if (i === 3) requests[i].observer.error(new Error('test missing file'));
    else { requests[i].observer.next(' text\0 '); requests[i].observer.complete(); }
  }
  assert.equal(requests.length, 36);
  assert.ok(peak <= 2);
  assert.equal(active, 0);
  assert.equal(context.result.text_lines[0], 'text');
  assert.equal(context.result.text_lines[3], '');
});
