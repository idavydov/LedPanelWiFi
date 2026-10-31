// Run: node --test tests/test_game_controls.cjs
// Exercise the actual component methods without connecting to any device.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('../web/node_modules/typescript');

const source = fs.readFileSync('web/src/app/components/tabs/tab-games/tab-games.component.ts', 'utf8');
function method(signature) {
  const start = source.indexOf(`  ${signature}(`);
  assert.ok(start >= 0, signature);
  let end = source.indexOf('{', start) + 1;
  let depth = 1;
  while (depth) {
    depth += (source[end] === '{') - (source[end] === '}');
    end++;
  }
  return source.slice(start, end);
}
const methods = ['btnPress', 'btnRelease', 'btnPointerDown', 'controlKeyDown', 'controlKeyUp',
  'repeatAction', 'btnUp', 'btnRight', 'btnDown', 'btnLeft', 'btnCenter', 'releaseInput'];

function controller() {
  const sent = [];
  const script = `class Controls {
    disabled = false; key_code = 0; last_time = 0; invert_left_right = false;
    socketService = {sendText: text => sent.push(text)};
    isDisabled() { return this.disabled; }
    ${methods.map(method).join('\n')}
  }
  result = new Controls();`;
  const js = ts.transpileModule(script, {compilerOptions: {target: ts.ScriptTarget.ES2022}}).outputText;
  const context = {sent, result: null, Date};
  vm.runInNewContext(js, context);
  return {controls: context.result, sent};
}

test('touch presses dispatch immediately and capture release outside the button', () => {
  const {controls, sent} = controller();
  let captured;
  let prevented = false;
  controls.btnPointerDown({button: 0, pointerId: 42, preventDefault() { prevented = true; },
    currentTarget: {setPointerCapture(id) { captured = id; }}}, 2);
  assert.equal(captured, 42);
  assert.ok(prevented);
  assert.deepEqual(sent, ['$3 11;']);
  controls.btnRelease(); // pointerup, pointercancel, or lostpointercapture
  controls.repeatAction();
  assert.equal(sent.length, 1);
});

test('disabled controls ignore pointer and keyboard input', () => {
  const {controls, sent} = controller();
  controls.disabled = true;
  controls.btnPointerDown({button: 0}, 1);
  controls.btnPress(3);
  assert.deepEqual(sent, []);
});

test('keyboard activation ignores native repeats and releases on focus loss', () => {
  const {controls, sent} = controller();
  const event = {key: ' ', repeat: false, preventDefault() {}, stopPropagation() {}};
  controls.controlKeyDown(event, 4);
  controls.controlKeyDown({...event, repeat: true}, 4);
  assert.deepEqual(sent, ['$3 13;']);
  controls.controlKeyUp(event);
  controls.repeatAction();
  assert.equal(sent.length, 1);
  controls.btnPress(1);
  controls.releaseInput();
  controls.repeatAction();
  assert.deepEqual(sent, ['$3 13;', '$3 10;']);
});
