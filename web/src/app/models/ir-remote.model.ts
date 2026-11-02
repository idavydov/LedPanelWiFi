export const IR_ACTIONS = [
  {id: 'up', label: 'Up / Rotate'},
  {id: 'right', label: 'Right'},
  {id: 'down', label: 'Down / Drop'},
  {id: 'left', label: 'Left'},
  {id: 'play', label: 'Start / Pause'},
  {id: 'next', label: 'Next game'},
  {id: 'maze', label: 'Choose Maze'},
  {id: 'snake', label: 'Choose Snake'},
  {id: 'tetris', label: 'Choose Tetris'},
  {id: 'arkanoid', label: 'Choose Arkanoid'},
  {id: 'effect_prev', label: 'Previous effect'},
  {id: 'effect_next', label: 'Next effect'},
  {id: 'power', label: 'Power on / off'},
] as const;

export interface IrBinding {
  id: string;
  action: string;
  protocol: string;
  bits: number;
  code: string;
}

export interface IrState {
  kind: 'state';
  pin: number;
  level: number;
  capacity: number;
  learning: string;
  notice: string;
  bindings: IrBinding[];
  uptime?: number;
  heap?: number;
  minHeap?: number;
  largestHeapBlock?: number;
  rssi?: number;
  resetReason?: string;
  effectBeforeReset?: string;
  effectName?: string;
  brightnessRaw?: number;
  indexMapActive?: boolean;
  mappedSlots?: number;
  logSkipped?: number;
}

export interface IrFrame {
  kind: 'frame';
  sequence: number;
  uptime: number;
  protocol: string;
  bits: number;
  code: string;
  key: string;
  repeat: boolean;
  held: boolean;
  overflow: boolean;
  rawLength: number;
  action: string;
  outcome: string;
  pulses: number[];
  skipped?: number;
}
