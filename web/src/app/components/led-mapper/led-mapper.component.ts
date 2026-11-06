import {Component, OnDestroy, OnInit} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {takeUntil, timer} from 'rxjs';
import {Base} from '../base.class';
import {WebsocketService} from '../../services/websocket/websocket.service';
import {formatLedPositions, LedPosition, parseLedPositions} from '../../models/led-mapping.model';

@Component({
  selector: 'app-led-mapper', standalone: true, imports: [FormsModule],
  templateUrl: './led-mapper.component.html', styleUrls: ['./led-mapper.component.scss'],
})
export class LedMapperComponent extends Base implements OnInit, OnDestroy {
  width = 20; height = 10; slot = 1; x = 0; y = 0;
  stringIndex = 0; stringCount = 1;
  stringSlots = [1, 1];
  text = ''; entries: LedPosition[] = []; error = ''; status = '';
  identifying = false; ready = false; busy = false; dirty = false;
  cells: {x: number; y: number; id?: number; string?: number}[] = [];
  keyboardEnabled = false;
  history: {text: string; slot: number; x: number; y: number; stringIndex: number; stringSlots: number[]}[] = [];
  private pending: LedPosition[] = [];
  private offset = 0;
  private awaiting = '';
  private deadline = 0;

  constructor(public socket: WebsocketService) { super(); }

  ngOnInit() {
    this.validate();
    this.socket.on<string>('mapping').pipe(takeUntil(this.destroy$)).subscribe(raw => {
      try {
        const data = JSON.parse(raw);
        if (data.kind === 'state') {
          this.ready = true;
          this.stringCount = data.strings === 2 ? 2 : 1;
          if (this.stringIndex >= this.stringCount) this.selectString(0);
          if (!this.dirty) {
            this.width = data.width; this.height = data.height; this.text = data.text;
            this.validate();
          }
          this.status = `Mapper connected: ${this.stringCount} string(s), 200 slots each. Origin (0,0) is bottom left.`;
        } else if (data.kind === 'error') {
          this.busy = false; this.error = data.error;
          if (data.op === 'identify') this.identifying = false;
        } else if (data.kind === 'saved') {
          this.busy = false; this.dirty = false; this.identifying = false;
          this.status = 'Map saved. The panel is restarting; reconnect and load the saved map to verify it.';
        } else if (data.kind === 'ack' && this.busy && data.op === this.awaiting) {
          this.sendNextChunk();
        }
      } catch { this.error = 'Could not read mapper response.'; }
    });
    this.socket.isConnected$.pipe(takeUntil(this.destroy$)).subscribe(connected => {
      this.ready = false;
      if (connected) this.send({op: 'state'});
      else {
        this.keyboardEnabled = false;
        this.identifying = false;
        if (this.busy) { this.busy = false; this.error = 'Connection lost while saving. Reload the active map to check whether it was saved.'; }
      }
    });
    timer(3000, 3000).pipe(takeUntil(this.destroy$)).subscribe(() => {
      if (this.identifying && this.socket.isConnected) this.identify();
      if (this.busy && Date.now() > this.deadline) {
        this.busy = false; this.error = 'Map save timed out. The current map can be checked with Load active map.';
      }
    });
  }

  send(message: object) { this.socket.send('mapping', JSON.stringify(message)); }

  validate() {
    this.error = '';
    try { this.entries = parseLedPositions(this.text, this.width, this.height); }
    catch (error) { this.error = (error as Error).message; this.entries = []; }
    this.cells = [];
    if (!Number.isInteger(this.width) || !Number.isInteger(this.height) || this.width < 8 || this.height < 8 ||
        this.width > 64 || this.height > 64 || this.width * this.height > 2048) return;
    const positions = new Map(this.entries.map(entry => [`${entry.x},${entry.y}`, entry]));
    for (let y = this.height - 1; y >= 0; y--) for (let x = 0; x < this.width; x++)
      this.cells.push({x, y, id: positions.get(`${x},${y}`)?.id, string: positions.get(`${x},${y}`)?.string});
  }

  edit(clearHistory = true) {
    if (clearHistory) this.history = [];
    this.dirty = true; this.validate();
  }
  identify() {
    if (!this.ready || !this.socket.isConnected || !Number.isInteger(this.slot) || this.slot < 1 || this.slot > 200) return;
    if (this.stringIndex >= this.stringCount) return;
    this.identifying = true; this.send({op: 'identify', string: this.stringIndex, id: this.slot});
  }
  stop() { this.identifying = false; this.send({op: 'stop'}); }
  selectSlot(value: number) {
    this.slot = Number.isFinite(value) ? Math.max(1, Math.min(200, Math.trunc(value))) : 1;
    this.stringSlots[this.stringIndex] = this.slot;
    const entry = this.entries.find(item => item.string === this.stringIndex && item.id === this.slot);
    if (entry) { this.x = entry.x; this.y = entry.y; }
    if (this.identifying) this.identify();
  }
  selectString(index: number) {
    if (this.busy || !this.ready || !this.socket.isConnected || !Number.isInteger(index) || index < 0 || index >= this.stringCount) return;
    this.stringSlots[this.stringIndex] = this.slot;
    this.stringIndex = index;
    this.slot = this.stringSlots[index];
    // Keep the shared anchor so neighboring LEDs can belong to either string.
    if (this.identifying) this.identify();
  }
  stepSlot(delta: number) {
    // Skipping factory IDs must not move the placement anchor.
    const x = this.x, y = this.y;
    this.selectSlot(this.slot + delta);
    this.x = x; this.y = y;
  }
  setKeyboard(enabled: boolean, panel: HTMLElement) {
    if (enabled && (!this.ready || !this.socket.isConnected || this.busy || this.error)) return;
    this.keyboardEnabled = enabled;
    if (enabled) {
      this.identify(); panel.focus();
      this.status = 'Keyboard ready. Enter places here; arrows place one cell away and advance the slot.';
    }
  }
  onKeydown(event: KeyboardEvent) {
    if (!this.keyboardEnabled || this.busy || !this.ready || !this.socket.isConnected ||
        event.ctrlKey || event.metaKey || event.altKey ||
        (event.target as HTMLElement)?.closest('input, textarea, select, [contenteditable]') ||
        (event.key === 'Enter' && (event.target as HTMLElement)?.closest('button'))) return;
    const directions: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1],
    };
    if (!directions[event.key] && !['+', '=', '-', '_', 'Enter', 'Escape', 'a', 'A', 'b', 'B'].includes(event.key)) return;
    event.preventDefault();
    if (event.repeat) return;
    if (directions[event.key]) this.moveAndAssign(...directions[event.key]);
    else if (event.key === '+' || event.key === '=') this.stepSlot(1);
    else if (event.key === '-' || event.key === '_') this.stepSlot(-1);
    else if (event.key === 'Enter') this.assign(true);
    else if (event.key.toLowerCase() === 'a') this.selectString(0);
    else if (event.key.toLowerCase() === 'b') this.selectString(1);
    else this.keyboardEnabled = false;
  }
  moveAndAssign(dx: number, dy: number) {
    if (this.busy || !this.ready || !this.socket.isConnected || this.error) return;
    const x = this.x, y = this.y;
    const nextX = x + dx, nextY = y + dy;
    if (nextX < 0 || nextY < 0 || nextX >= this.width || nextY >= this.height) {
      this.status = 'Outside the canvas. The slot has not advanced.'; return;
    }
    this.x = nextX; this.y = nextY;
    if (!this.assign(true)) { this.x = x; this.y = y; }
    else {
      const previous = this.history[this.history.length - 1];
      previous.x = x; previous.y = y;
    }
  }
  assign(next = false) {
    if (this.error || this.busy || !this.ready || !this.socket.isConnected) return false;
    const entries = [...this.entries.filter(item => item.string !== this.stringIndex || item.id !== this.slot),
      {string: this.stringIndex, id: this.slot, x: this.x, y: this.y}];
    try {
      const text = formatLedPositions(entries);
      parseLedPositions(text, this.width, this.height);
      if (entries.some(item => item.string >= this.stringCount)) throw new Error('Install the two-string firmware before assigning string B.');
      this.history.push({text: this.text, slot: this.slot, x: this.x, y: this.y,
        stringIndex: this.stringIndex, stringSlots: [...this.stringSlots]});
      this.text = text; this.edit(false);
      this.status = `Assigned ${this.stringIndex ? 'B' : 'A'}${this.slot} to (${this.x},${this.y}).`;
      if (next) {
        this.identifying = true;
        if (this.slot < 200) this.stepSlot(1);
        else {
          this.keyboardEnabled = false; this.identify();
          this.status += ' Reached slot 200; assignment paused.';
        }
      }
      return true;
    } catch (error) { this.status = (error as Error).message; return false; }
  }
  undo() {
    if (this.busy || !this.socket.isConnected) return;
    const previous = this.history.pop();
    if (!previous) return;
    this.text = previous.text; this.slot = previous.slot; this.x = previous.x; this.y = previous.y;
    this.stringIndex = previous.stringIndex; this.stringSlots = previous.stringSlots;
    this.edit(false); if (this.identifying) this.identify();
    this.status = `Undid assignment; ${this.stringIndex ? 'B' : 'A'}${this.slot} selected.`;
  }
  skip() {
    if (this.error || this.busy || !this.ready || !this.socket.isConnected) return;
    this.history.push({text: this.text, slot: this.slot, x: this.x, y: this.y,
      stringIndex: this.stringIndex, stringSlots: [...this.stringSlots]});
    this.text = formatLedPositions(this.entries.filter(item => item.string !== this.stringIndex || item.id !== this.slot));
    this.edit(false); this.stepSlot(1);
  }
  chooseCell(x: number, y: number) {
    if (this.busy || !this.ready || !this.socket.isConnected) return;
    this.x = x; this.y = y;
    const entry = this.entries.find(item => item.x === x && item.y === y);
    if (entry && entry.string < this.stringCount) {
      this.selectString(entry.string); this.selectSlot(entry.id);
    }
  }
  mappedOnString(index: number) { return this.entries.filter(item => item.string === index).length; }
  load() {
    this.history = []; this.keyboardEnabled = false;
    this.dirty = false; this.status = 'Loading active map…';
    this.send({op: 'state'});
  }
  download() {
    const url = URL.createObjectURL(new Blob([this.text + '\n'], {type: 'text/plain'}));
    const link = document.createElement('a'); link.href = url; link.download = 'led-positions.txt'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async importFile(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      if (file.size > 10000) { this.error = 'Position file is too large (maximum 10 KB).'; return; }
      this.history = []; this.keyboardEnabled = false;
      this.text = await file.text(); this.edit();
    }
    input.value = '';
  }
  save() {
    this.validate();
    if (this.error || !this.ready || !this.socket.isConnected || this.busy || !this.entries.length) return;
    if (this.entries.some(item => item.string >= this.stringCount)) {
      this.error = 'Install the two-string firmware before saving string B.'; return;
    }
    this.stop(); this.pending = [...this.entries]; this.offset = 0; this.busy = true;
    this.awaiting = 'begin'; this.deadline = Date.now() + 15000;
    this.status = 'Saving map…';
    this.send({op: 'begin', width: this.width, height: this.height});
  }
  private sendNextChunk() {
    this.deadline = Date.now() + 15000;
    if (this.offset < this.pending.length) {
      const rows = this.pending.slice(this.offset, this.offset + 10).map(item =>
        this.stringCount === 2 ? [item.string, item.id, item.x, item.y] : [item.id, item.x, item.y]);
      this.offset += rows.length; this.awaiting = 'chunk'; this.send({op: 'chunk', rows});
    } else { this.awaiting = 'commit'; this.send({op: 'commit'}); }
  }
  override ngOnDestroy() { this.stop(); super.ngOnDestroy(); }
}
