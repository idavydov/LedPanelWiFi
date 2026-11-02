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
    width=20; height=10; slot=1; x=0; y=0; text=''; entries=[]; cells=[];
    error=''; status=''; dirty=false; busy=false; ready=true; identifying=false;
    pending=[]; offset=0; awaiting=''; deadline=0;
    socket={isConnected:true, send:(topic,text)=>sent.push({topic,...JSON.parse(text)})};
    ${['send','validate','edit','identify','stop','selectSlot','assign','skip','chooseCell','save'].map(method).join('\n')}
    ${method('private sendNextChunk').replace('private ', '')}
  }
  result = new Mapper();`;
  const context = {result: null, sent, parseLedPositions, formatLedPositions, Date, Map, Number};
  vm.runInNewContext(ts.transpileModule(script, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText, context);
  return {mapper: context.result, sent};
}

test('explicit factory IDs preserve gaps, slot 200, and bottom-left coordinates', () => {
  const entries = parseLedPositions('# shape\r\n7:0,1\r\n8:0,2\r\n200:5,8', 20, 10);
  assert.equal(formatLedPositions(entries), '7:0,1\n8:0,2\n200:5,8');
  assert.equal(entries.length, 3);
  for (const text of ['0:0,0', '201:0,0', '7:20,0', '7:0,10', '7:-1,0', '7:0.5,1',
    '7:0,0\n7:1,1', '7:0,0\n8:0,0', '-']) assert.throws(() => parseLedPositions(text, 20, 10));
  assert.throws(() => parseLedPositions('1:0,0', 64, 64));
});

test('identification follows selected slot and skip does not renumber later entries', () => {
  const {mapper, sent} = controller();
  mapper.text = '7:0,1\n8:0,2\n200:5,8'; mapper.validate();
  mapper.selectSlot(7); mapper.identify();
  assert.equal(sent.at(-1).id, 7);
  mapper.skip();
  assert.equal(mapper.slot, 8);
  assert.equal(sent.at(-1).id, 8);
  assert.equal(mapper.text, '8:0,2\n200:5,8');
  mapper.x = 5; mapper.y = 8; mapper.assign();
  assert.equal(mapper.text, '8:0,2\n200:5,8'); // duplicate coordinate refused
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
