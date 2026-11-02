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
  text = ''; entries: LedPosition[] = []; error = ''; status = '';
  identifying = false; ready = false; busy = false; dirty = false;
  cells: {x: number; y: number; id?: number}[] = [];
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
          if (!this.dirty) {
            this.width = data.width; this.height = data.height; this.text = data.text;
            this.validate();
          }
          this.status = 'Mapper connected. Factory slots 1–200; origin (0,0) is bottom left.';
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
    const positions = new Map(this.entries.map(entry => [`${entry.x},${entry.y}`, entry.id]));
    for (let y = this.height - 1; y >= 0; y--) for (let x = 0; x < this.width; x++)
      this.cells.push({x, y, id: positions.get(`${x},${y}`)});
  }

  edit() { this.dirty = true; this.validate(); }
  identify() {
    if (!this.ready || !this.socket.isConnected || !Number.isInteger(this.slot) || this.slot < 1 || this.slot > 200) return;
    this.identifying = true; this.send({op: 'identify', id: this.slot});
  }
  stop() { this.identifying = false; this.send({op: 'stop'}); }
  selectSlot(value: number) {
    this.slot = Number.isFinite(value) ? Math.max(1, Math.min(200, Math.trunc(value))) : 1;
    const entry = this.entries.find(item => item.id === this.slot);
    if (entry) { this.x = entry.x; this.y = entry.y; }
    if (this.identifying) this.identify();
  }
  assign(next = false) {
    if (this.error) return;
    const entries = [...this.entries.filter(item => item.id !== this.slot), {id: this.slot, x: this.x, y: this.y}];
    try {
      const text = formatLedPositions(entries);
      parseLedPositions(text, this.width, this.height);
      this.text = text; this.edit();
      if (next) this.selectSlot(this.slot + 1);
    } catch (error) { this.status = (error as Error).message; }
  }
  skip() {
    if (this.error) return;
    this.text = formatLedPositions(this.entries.filter(item => item.id !== this.slot));
    this.edit(); this.selectSlot(this.slot + 1);
  }
  chooseCell(x: number, y: number) { this.x = x; this.y = y; }
  load() {
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
      this.text = await file.text(); this.edit();
    }
    input.value = '';
  }
  save() {
    this.validate();
    if (this.error || !this.ready || !this.socket.isConnected || this.busy || !this.entries.length) return;
    this.stop(); this.pending = [...this.entries]; this.offset = 0; this.busy = true;
    this.awaiting = 'begin'; this.deadline = Date.now() + 15000;
    this.status = 'Saving map…';
    this.send({op: 'begin', width: this.width, height: this.height});
  }
  private sendNextChunk() {
    this.deadline = Date.now() + 15000;
    if (this.offset < this.pending.length) {
      const rows = this.pending.slice(this.offset, this.offset + 10).map(item => [item.id, item.x, item.y]);
      this.offset += rows.length; this.awaiting = 'chunk'; this.send({op: 'chunk', rows});
    } else { this.awaiting = 'commit'; this.send({op: 'commit'}); }
  }
  override ngOnDestroy() { this.stop(); super.ngOnDestroy(); }
}
