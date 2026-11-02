// Run: node tests/test_matrix_settings.cjs. No device or browser connection.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('../web/node_modules/typescript');
const source = fs.readFileSync('web/src/app/components/tabs/tab-matrix/tab-matrix.component.ts', 'utf8');

function method(name) {
  const start = source.indexOf(`  ${name}(`);
  assert.ok(start >= 0, name);
  let end = source.indexOf('{', start) + 1;
  let depth = 1;
  while (depth) {
    depth += (source[end] === '{') - (source[end] === '}');
    end++;
  }
  return source.slice(start, end);
}

function controller() {
  const context = {result: null, sent: []};
  const script = `class Matrix {
    index_files = []; index_file = -1; radio_idx = 0;
    socketService = {isConnected: true, sendText: text => sent.push(text)};
    managementService = {state: {}};
    matrixPlugger = {type: 1, angle: 0, direction: 0};
    totalPlugger = {type: 1, angle: 0, direction: 0};
    segWidthFormControl = {value: 20}; segHeightFormControl = {value: 10};
    tolWidthFormControl = {value: 1}; tolHeightFormControl = {value: 1};
    ${['isDisabled', 'normalizeIndexSelection', 'hasSelectedIndexMap', 'getMatrixSize', 'applyMatrixSettings'].map(method).join('\n')}
  }
  result = new Matrix();`;
  vm.runInNewContext(ts.transpileModule(script, {
    compilerOptions: {target: ts.ScriptTarget.ES2022}
  }).outputText, context);
  return {matrix: context.result, sent: context.sent};
}

test('empty map list and stale index cannot crash the matrix page or send settings', () => {
  const {matrix, sent} = controller();
  matrix.normalizeIndexSelection();
  assert.equal(matrix.index_file, -1);
  assert.equal(matrix.getMatrixSize(), '—');
  matrix.applyMatrixSettings({});
  assert.equal(sent.length, 0);
  matrix.index_files = [{value: 0, displayText: '20x10'}];
  assert.equal(matrix.getMatrixSize(), '—'); // list can arrive before current selection
  matrix.normalizeIndexSelection();
  assert.equal(matrix.getMatrixSize(), '20 x 10');
  matrix.applyMatrixSettings({});
  assert.equal(sent[0], '$2 20 10 2 0 0 1 1 1 0 0 0;');
});

test('segment mode remains usable without a map and disconnected controls send nothing', () => {
  const {matrix, sent} = controller();
  matrix.radio_idx = 1;
  assert.equal(matrix.getMatrixSize(), '20 x 10');
  matrix.applyMatrixSettings({});
  assert.equal(sent.length, 1);
  matrix.socketService.isConnected = false;
  matrix.applyMatrixSettings({});
  assert.equal(sent.length, 1);
});

test('empty M10 payload does not produce a phantom blank map option', () => {
  const model = fs.readFileSync('web/src/app/models/state.model.ts', 'utf8');
  const start = model.indexOf("      case 'M10': {");
  const end = model.indexOf("      case 'M11':", start);
  const script = `class ComboBoxItem { constructor(public displayText: string, public value: number) {} }
    function parse(value) { switch ('M10') { ${model.slice(start, end)} } }
    result = {map_idx_list: []}; parse.call(result, payload);`;
  for (const [payload, expected] of [['', []], [' ,  ', []], ['20x10, 10x20', ['20x10', '10x20']]]) {
    const context = {result: null, payload};
    vm.runInNewContext(ts.transpileModule(script, {}).outputText, context);
    assert.deepEqual(Array.from(context.result.map_idx_list, item => item.displayText), expected);
  }
});
