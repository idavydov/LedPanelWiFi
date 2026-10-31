import {Component, OnDestroy, OnInit} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {distinctUntilChanged, takeUntil, timer} from 'rxjs';
import {Base} from '../../base.class';
import {WebsocketService} from '../../../services/websocket/websocket.service';
import {IR_ACTIONS, IrBinding, IrFrame, IrState} from '../../../models/ir-remote.model';

@Component({
  selector: 'app-tab-ir-remote',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './tab-ir-remote.component.html',
  styleUrls: ['./tab-ir-remote.component.scss'],
})
export class TabIrRemoteComponent extends Base implements OnInit, OnDestroy {
  readonly irActions = IR_ACTIONS;
  irState: IrState | null = null;
  irFrames: IrFrame[] = [];
  irListening = true;
  irError = '';

  constructor(public socketService: WebsocketService) { super(); }

  ngOnInit() {
    this.socketService.on<string>('ir')
      .pipe(takeUntil(this.destroy$))
      .subscribe((data) => {
        try {
          const message = JSON.parse(data) as IrState | IrFrame;
          if (message.kind === 'state') {
            this.irState = message;
            this.irError = '';
          } else if (message.kind === 'frame' && this.irListening) {
            this.irFrames = [message, ...this.irFrames].slice(0, 20);
          }
        } catch {
          this.irError = 'Could not read IR receiver status.';
        }
      });

    timer(0, 5000).pipe(takeUntil(this.destroy$)).subscribe(() => this.refreshIR());

    this.socketService.isConnected$.pipe(takeUntil(this.destroy$), distinctUntilChanged())
      .subscribe(connected => {
        if (connected) this.refreshIR();
        else { this.irState = null; this.irFrames = []; }
      });
  }

  setDebugBrightness() {
    this.socketService.sendText('$4 0 3;');
  }

  formatBytes(value?: number): string {
    return value == null ? '—' : `${(value / 1024).toFixed(1)} KiB`;
  }

  refreshIR() {
    if (this.socketService.isConnected) {
      this.socketService.send('ir', JSON.stringify({op: 'state', watch: this.irListening}));
    }
  }

  learnIR(action: string) {
    this.irListening = true;
    this.refreshIR();
    this.socketService.send('ir', JSON.stringify({op: 'learn', action}));
  }

  cancelIRLearning() {
    this.socketService.send('ir', JSON.stringify({op: 'cancel'}));
  }

  removeIR(binding: IrBinding) {
    this.socketService.send('ir', JSON.stringify({op: 'remove', id: binding.id}));
  }

  irBindingsFor(action: string): IrBinding[] {
    return this.irState?.bindings.filter(binding => binding.action === action) ?? [];
  }

  irActionLabel(action: string): string {
    return this.irActions.find(item => item.id === action)?.label ?? 'None';
  }

  override ngOnDestroy() {
    this.cancelIRLearning();
    this.socketService.send('ir', JSON.stringify({op: 'state', watch: false}));
    super.ngOnDestroy();
  }

}
