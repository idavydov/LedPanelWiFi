// Run: node tests/test_led_mapper.cjs. Exercise the actual parser and mapper methods.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('../web/node_modules/typescript');
const modelSource = fs.readFileSync('web/src/app/models/led-mapping.model.ts', 'utf8');
const source = fs.readFileSync('web/src/app/components/led-mapper/led-mapper.component.ts', 'utf8');
const model = {exports: {}};
vm.runInNewContext(ts.transpileModule(modelSource, {
  compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}
}).outputText, model);
const {parseLedPositions, formatLedPositions} = model.exports;

function method(name) {
  const start = source.indexOf(`  ${name}(`);
  assert.ok(start >= 0, name);
  let end = source.indexOf('{', start) + 1, depth = 1;
  while (depth) { depth += (source[end] === '{') - (source[end] === '}'); end++; }
  return source.slice(start, end);
}

function controller() {
  const sent = [];
  const script = `class Mapper {
    width=20; height=10; slot=1; x=0; y=0; stringIndex=0; stringCount=2; stringSlots=[1,1]; text=''; entries=[]; cells=[];
    error=''; status=''; dirty=false; busy=false; ready=true; identifying=false;
    keyboardEnabled=false; history=[];
    pending=[]; offset=0; awaiting=''; deadline=0;
    socket={isConnected:true, send:(topic,text)=>sent.push({topic,...JSON.parse(text)})};
    ${['send','validate','edit','identify','stop','selectSlot','selectString','stepSlot','setKeyboard','onKeydown','moveAndAssign','assign','undo','skip','chooseCell','save'].map(method).join('\n')}
    ${method('private sendNextChunk').replace('private ', '')}
  }
  result = new Mapper();`;
  const context = {result: null, sent, parseLedPositions, formatLedPositions, Date, Map, Number};
  vm.runInNewContext(ts.transpileModule(script, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText, context);
  return {mapper: context.result, sent};
}

test('explicit factory IDs preserve gaps, slot 200, and bottom-left coordinates', () => {
  const entries = parseLedPositions('# shape\r\n7:0,1\r\n8:0,2\r\n200:5,8', 20, 10);
  assert.equal(formatLedPositions(entries), 'A7:0,1\nA8:0,2\nA200:5,8');
  assert.equal(entries.length, 3);
  for (const text of ['0:0,0', '201:0,0', '7:20,0', '7:0,10', '7:-1,0', '7:0.5,1',
    '7:0,0\n7:1,1', '7:0,0\n8:0,0', '-']) assert.throws(() => parseLedPositions(text, 20, 10));
  assert.throws(() => parseLedPositions('1:0,0', 64, 64));
});

function key(mapper, name, extra = {}) {
  let prevented = false;
  mapper.onKeydown({key: name, repeat: false, target: {closest: () => null},
    preventDefault: () => { prevented = true; }, ...extra});
  return prevented;
}

test('keyboard places first LED then walks all directions and identifies the next factory ID', () => {
  const {mapper, sent} = controller();
  mapper.slot = 7; mapper.x = 3; mapper.y = 3;
  let focused = false;
  mapper.setKeyboard(true, {focus: () => { focused = true; }});
  assert.equal(focused, true); assert.equal(sent.at(-1).id, 7);
  assert.equal(key(mapper, 'Enter'), true);
  for (const direction of ['ArrowRight', 'ArrowUp', 'ArrowLeft', 'ArrowUp', 'ArrowDown']) {
    key(mapper, direction);
  }
  // The final Down collides with slot 10 and must not overwrite it or advance.
  assert.equal(mapper.text, 'A7:3,3\nA8:4,3\nA9:4,4\nA10:3,4\nA11:3,5');
  assert.equal(mapper.slot, 12); assert.equal(sent.at(-1).id, 12);
  assert.equal(mapper.x, 3); assert.equal(mapper.y, 5);
  assert.match(mapper.status, /assigned twice/);
  mapper.undo();
  assert.equal(mapper.slot, 11); assert.equal(mapper.y, 4);
  assert.equal(mapper.text, 'A7:3,3\nA8:4,3\nA9:4,4\nA10:3,4');
  assert.equal(sent.at(-1).id, 11);
});

test('plus and minus change only ID, preserving anchor even across existing assignments', () => {
  const {mapper, sent} = controller();
  mapper.text = '8:9,8'; mapper.validate(); mapper.slot = 7;
  mapper.x = 2; mapper.y = 3; mapper.keyboardEnabled = true; mapper.identifying = true;
  for (const name of ['+', '-', '=', '_']) key(mapper, name);
  assert.equal(mapper.slot, 7); assert.equal(mapper.x, 2); assert.equal(mapper.y, 3);
  assert.equal(mapper.text, '8:9,8'); assert.equal(sent.at(-1).id, 7);
  mapper.slot = 200; key(mapper, '+'); assert.equal(mapper.slot, 200);
  mapper.slot = 1; key(mapper, '-'); assert.equal(mapper.slot, 1);
});

test('shortcuts ignore held keys, form inputs, modifiers and inactive sessions', () => {
  const {mapper, sent} = controller(); mapper.x = 2; mapper.y = 2;
  assert.equal(key(mapper, 'ArrowRight'), false);
  mapper.keyboardEnabled = true;
  assert.equal(key(mapper, 'ArrowRight', {repeat: true}), true);
  for (const extra of [{ctrlKey: true}, {metaKey: true}, {altKey: true},
    {target: {closest: () => ({tagName: 'INPUT'})}}]) {
    assert.equal(key(mapper, 'ArrowRight', extra), false);
  }
  mapper.busy = true; assert.equal(key(mapper, 'Enter'), false);
  mapper.busy = false; mapper.socket.isConnected = false;
  assert.equal(key(mapper, 'ArrowRight'), false);
  mapper.socket.isConnected = true; mapper.ready = false;
  assert.equal(key(mapper, 'Enter'), false);
  assert.equal(mapper.slot, 1); assert.equal(mapper.text, ''); assert.equal(sent.length, 0);
  mapper.ready = true; key(mapper, 'Escape'); assert.equal(mapper.keyboardEnabled, false);
});

test('mouse directions share placement rules, reject boundaries, and stop keyboard at slot 200', () => {
  const {mapper} = controller();
  mapper.moveAndAssign(-1, 0); assert.equal(mapper.slot, 1); assert.equal(mapper.text, '');
  mapper.moveAndAssign(1, 0);
  assert.equal(mapper.text, 'A1:1,0'); assert.equal(mapper.slot, 2);
  mapper.undo(); assert.equal(mapper.text, ''); assert.equal(mapper.slot, 1); assert.equal(mapper.x, 0);
  mapper.slot = 200; mapper.keyboardEnabled = true;
  mapper.moveAndAssign(0, 1);
  assert.equal(mapper.text, 'A200:0,1'); assert.equal(mapper.slot, 200);
  assert.equal(mapper.keyboardEnabled, false);
  key(mapper, 'ArrowRight'); assert.equal(mapper.text, 'A200:0,1');
});

test('identification follows selected slot and skip does not renumber later entries', () => {
  const {mapper, sent} = controller();
  mapper.text = '7:0,1\n8:0,2\n200:5,8'; mapper.validate();
  mapper.selectSlot(7); mapper.identify();
  assert.equal(sent.at(-1).id, 7);
  mapper.skip();
  assert.equal(mapper.slot, 8);
  assert.equal(sent.at(-1).id, 8);
  assert.equal(mapper.text, 'A8:0,2\nA200:5,8');
  mapper.x = 5; mapper.y = 8; mapper.assign();
  assert.equal(mapper.text, 'A8:0,2\nA200:5,8'); // duplicate coordinate refused
  mapper.stop(); assert.equal(sent.at(-1).op, 'stop');
});

test('save uses bounded chunks and does not send invalid drafts', () => {
  const {mapper, sent} = controller();
  mapper.text = Array.from({length: 25}, (_, i) => `${i + 1}:${i % 20},${Math.floor(i / 20)}`).join('\n');
  mapper.save();
  assert.equal(mapper.busy, true);
  assert.equal(sent.at(-1).op, 'begin');
  mapper.sendNextChunk(); mapper.sendNextChunk(); mapper.sendNextChunk(); mapper.sendNextChunk();
  assert.deepEqual(sent.filter(item => item.op === 'chunk').map(item => item.rows.length), [10, 10, 5]);
  assert.equal(sent.at(-1).op, 'commit');
  for (const message of sent) assert.ok(JSON.stringify(message).length < 1024);
  mapper.busy = false; mapper.text = '1:0,0\n2:0,0';
  const before = sent.length; mapper.save();
  assert.equal(sent.length, before);
});

test('A and B keep factory IDs independent, migrate plain IDs, and reject cross-string collisions', () => {
  const entries = parseLedPositions('7:0,0\nB7:1,0\na200:2,0\nb200:3,0', 20, 10);
  assert.equal(formatLedPositions(entries), 'A7:0,0\nA200:2,0\nB7:1,0\nB200:3,0');
  for (const text of ['A7:0,0\n7:1,0', 'A7:0,0\nB7:0,0', 'C7:0,0', 'B201:0,0']) {
    assert.throws(() => parseLedPositions(text, 20, 10));
  }
});

test('switching strings remembers each cursor, keeps anchor, and identifies only the active output', () => {
  const {mapper, sent} = controller();
  mapper.selectSlot(7); mapper.x = 3; mapper.y = 3;
  mapper.keyboardEnabled = true; mapper.identifying = true;
  key(mapper, 'Enter'); // A7 at anchor, next A8
  key(mapper, 'b'); assert.equal(mapper.slot, 1); assert.equal(mapper.x, 3); assert.equal(mapper.y, 3);
  assert.equal(sent.at(-1).string, 1); assert.equal(sent.at(-1).id, 1);
  mapper.selectSlot(7); key(mapper, 'ArrowRight'); // B7 next to A7, next B8
  key(mapper, 'a'); assert.equal(mapper.slot, 8); assert.equal(mapper.x, 4);
  key(mapper, 'ArrowUp'); // A8 above B7
  assert.equal(mapper.text, 'A7:3,3\nA8:4,4\nB7:4,3');
  key(mapper, 'B'); assert.equal(mapper.slot, 8);
  key(mapper, 'ArrowDown'); // collision with B7; no overwrite/advance
  assert.equal(mapper.slot, 8); assert.equal(mapper.y, 4);
  mapper.undo(); // restore state before A8 placement, including its original anchor
  assert.equal(mapper.stringIndex, 0); assert.equal(mapper.slot, 8);
  assert.equal(mapper.x, 4); assert.equal(mapper.y, 3);
  assert.equal(mapper.text, 'A7:3,3\nB7:4,3');
  mapper.chooseCell(4, 3); assert.equal(mapper.stringIndex, 1); assert.equal(mapper.slot, 7);
  assert.equal(sent.at(-1).string, 1); assert.equal(sent.at(-1).id, 7);
  mapper.skip(); assert.equal(mapper.text, 'A7:3,3'); // A7 is independent of B7
});

test('new saves include string IDs; older firmware accepts only A and receives legacy triples', () => {
  const {mapper, sent} = controller();
  mapper.text = 'A200:0,0\nB200:1,0'; mapper.save(); mapper.sendNextChunk();
  assert.equal(JSON.stringify(sent.at(-1).rows), '[[0,200,0,0],[1,200,1,0]]');
  mapper.busy = false; mapper.stringCount = 1; mapper.ready = true; mapper.error = '';
  let before = sent.length; mapper.save(); assert.equal(sent.length, before);
  assert.match(mapper.error, /two-string firmware/);
  mapper.text = 'A200:0,0'; mapper.error = ''; mapper.save(); mapper.sendNextChunk();
  assert.equal(JSON.stringify(sent.at(-1).rows), '[[200,0,0]]');
  mapper.busy = false; mapper.stringIndex = 0; mapper.slot = 200;
  mapper.selectString(1); assert.equal(mapper.stringIndex, 0);
});
