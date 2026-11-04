import {Injectable, OnDestroy} from '@angular/core';
import {BehaviorSubject, catchError, interval, Observable, Subject, throwError as observableThrowError, Subscription, takeUntil, tap} from 'rxjs';
import {distinctUntilChanged, filter, map, share} from 'rxjs/operators';
import {WebSocketSubject, WebSocketSubjectConfig} from 'rxjs/webSocket';
import {environment} from "../../../environments/environment";
import {Base} from "../../components/base.class";
import {HttpClient, HttpHeaders} from "@angular/common/http";

export const WS = {
  // 'Топики' получения состояния из устройства
  ON: {
    // @formatter:off
    STATE:   'stt',   //- сообщения о текущем статусе параметров устройства - индивидуальный режим
    DATA:    'dta',	  // - отправка запрошенных данных клиенту, в ответ на полученную команду, например '$6 7
    ERROR:   'err',	  // - уведомления об ошибке клиенту
    ALARM:   'alm',	  // - сообщения о событиях будильника
    AMODE:   'amd',	  // - сообщения о наступлении событий авторежимов по времени
    WEATHER: 'wtr',	  // - сообщения о получении актуальной погоды
    TIME:    'tme',	  // - сообщения о синхронизации времени
    SDCARD:  'sdc',	  // - сообщения о событиях SD-карты (загрузка файла эффекта)
    TEXT:    'txt',	  // - сообщения о событиях бегущей строки - запуск, окончание
    E131:    'e131',  // - сообщения о событиях синхронизации между матрицами
    EDT:     'edt'	  // - сообщения c параметрами редактируемого эффекта
    // @formatter:on
  },
  // 'Топики' отправки команд в устройство
  SEND: {
    COMMAND: 'cmd'
  }
};

export interface IWebsocketService {
  on<T>(event: string): Observable<T>;

  send(event: string, data: any): void;

  sendText(text: string): void;

  status$: Observable<boolean>;
}

export interface IWsMessage<T> {
  e: string;
  d: T;
}

@Injectable({
  providedIn: 'root'
})
export class WebsocketService extends Base implements IWebsocketService, OnDestroy {

  public host: string = environment.production ? window.location.hostname : '192.168.0.100';

  private websocket$: WebSocketSubject<IWsMessage<any>> | null = null;
  private connectionState$ = new BehaviorSubject<boolean>(false);
  private wsMessages$ = new Subject<IWsMessage<any>>();
  private url = `ws://${this.host}/ws`;
  private pingInterval = 30000;
  private reconnectInterval = 5000;
  private lastReceivedAt = Date.now();
  private lastHeartbeatAt = Date.now();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private webSocketSubscription: Subscription | null = null;
  private destroyed = false;

  // -------------------------------------

  public firstConnect = true;
  public isConnected = false;
  public isConnected$ = new BehaviorSubject<boolean>(false);
  public lastClose: {code: number; reason: string} | null = null;

  // статус соединения
  public status$: Observable<boolean>;

  // -------------------------------------

  constructor(private httpClient: HttpClient) {
    super();
    this.status$ = this.connectionState$.asObservable().pipe(distinctUntilChanged());
    this.status$.pipe(takeUntil(this.destroy$)).subscribe(connected => {
      if (this.isConnected !== connected) {
        this.isConnected = connected;
        this.isConnected$.next(connected);
      }
      document.body.classList.toggle('noscroll', !connected);
    });
    interval(this.pingInterval).pipe(takeUntil(this.destroy$)).subscribe(() => this.checkHeartbeat());
    this.connect();
  }

  private connect(): void {
    if (this.destroyed || this.websocket$) return;
    let socket: WebSocketSubject<IWsMessage<any>>;
    const config: WebSocketSubjectConfig<IWsMessage<any>> = {
      url: this.url,
      openObserver: {next: () => {
        if (this.websocket$ !== socket) return;
        this.lastReceivedAt = this.lastHeartbeatAt = Date.now();
        this.connectionState$.next(true);
        this.firstConnect = false;
        this.ping();
      }},
      closeObserver: {next: (event: CloseEvent) => {
        if (this.websocket$ !== socket) return;
        this.lastClose = {code: event.code, reason: event.reason};
        this.connectionClosed(socket);
      }},
    };
    socket = new WebSocketSubject(config);
    this.websocket$ = socket;
    const subscription = socket.pipe(takeUntil(this.destroy$)).subscribe({
      next: message => {
        if (this.websocket$ !== socket) return;
        this.pong(); // Any received frame proves the connection is alive.
        this.wsMessages$.next(message);
      },
      error: () => {
        if (this.websocket$ !== socket) return;
        this.lastClose = {code: 1006, reason: 'WebSocket transport failed'};
        this.connectionClosed(socket);
      },
      complete: () => this.connectionClosed(socket),
    });
    if (this.websocket$ === socket) this.webSocketSubscription = subscription;
    else subscription.unsubscribe();
  }

  private connectionClosed(socket: WebSocketSubject<IWsMessage<any>>): void {
    if (this.websocket$ !== socket) return; // Ignore late events from a replaced socket.
    this.websocket$ = null;
    this.webSocketSubscription?.unsubscribe();
    this.webSocketSubscription = null;
    this.connectionState$.next(false);
    this.reconnect();
  }

  private disconnect(): void {
    const socket = this.websocket$;
    this.websocket$ = null;
    this.webSocketSubscription?.unsubscribe();
    this.webSocketSubscription = null;
    socket?.complete();
    this.connectionState$.next(false);
    this.reconnect();
  }

  private reconnect(): void {
    if (this.destroyed || this.websocket$ || this.reconnectTimer !== null) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectInterval);
  }

  private checkHeartbeat(): void {
    const now = Date.now();
    const lateTimer = now - this.lastHeartbeatAt > this.pingInterval * 2;
    this.lastHeartbeatAt = now;
    // Background/suspended browser tabs get a fresh probe after waking up.
    if (lateTimer) this.lastReceivedAt = now;
    if (this.isConnected && now - this.lastReceivedAt >= this.pingInterval * 2) {
      this.lastClose = {code: 0, reason: 'No server data for 60 seconds (client heartbeat timeout)'};
      this.disconnect();
      return;
    }
    this.ping();
  }

  private ping(): void {
    if (this.isConnected && this.websocket$) {
      this.websocket$.next({e: 'cmd', d: '$6 7|FM|UP'});
    } else if (!this.websocket$) this.reconnect();
  }

  public pong(): void {
    this.lastReceivedAt = Date.now();
  }

  /*
  * on message event
  * */
  public on = <T>(event: string): Observable<T> => {
    return this.wsMessages$.pipe(
      filter((message: IWsMessage<any>) => message.e === event),
      map((message: IWsMessage<any>) => message.d)
    );
  };

  /*
  * on message to server
  * */
  public send(event: string, data: any = {}): void {
    if (this.isConnected) {
      if (event === WS.SEND.COMMAND || event === 'ir' || event === 'mapping') {
        this.websocket$?.next({e: event, d: data});
      }
    }
  }

  /*
  * on send text command message to server
  * */
  public sendText(text: string): void {
    this.send(WS.SEND.COMMAND, text);
  }

  public getFile(fileName: string): Observable<any> {

    let contentType: string;
    // https://github.com/angular/angular/issues/18586
    const reForFilenameExtension = /(?:\.([^.]+))?$/;
    // @ts-ignore
    const ext = reForFilenameExtension.exec(fileName)[1];
    switch (ext) {
      case 'json':
        contentType = 'text/plain';
        break;
      //   https://stackoverflow.com/questions/25727306/request-header-field-access-control-allow-headers-is-not-allowed-by-access-contr
      case 'tar':
      case 'tgz':
        contentType = 'application/x-www-form-urlencoded; charset=UTF-8';
        break;
      case 'txt':
        contentType = 'text/plain';
        break;
      default:
        contentType = 'text/plain';
        break;
    }

    const headers = new HttpHeaders().set('content-type', contentType).set('Cache-Control', 'no-cache, no-store, must-revalidate, post-check=0, pre-check=0').set('Pragma', 'no-cache');
    const url = `http://${this.host}/${fileName}`;

    switch (ext) {
      case 'json':
        contentType = 'text/plain';
        return this.httpClient.get(url, { headers: headers, responseType: 'json' })
          .pipe(
            map(response => response),
            tap(response => this.logResponse('getFile', 'getFile()', url, '', '', response)),
            catchError(error => {
              return observableThrowError(error);
            }));

      case 'tar':
      case 'tgz':
        contentType = 'application/x-www-form-urlencoded; charset=UTF-8';
        return this.httpClient.get(url, { headers: headers, responseType: 'blob' })
          .pipe(
            map(response => response),
            tap(response => this.logResponse('getFile', 'getFile()', url, '', '', response)),
            catchError(error => {
              return observableThrowError(error);
            }));

      case 'txt':
        contentType = 'text/plain';
        return this.httpClient.get(url, { headers: headers, responseType: 'text' })
          .pipe(
            map(response => response),
            tap(response => this.logResponse('getFile', 'getFile()', url, '', '', response)),
            catchError(error => {
              return observableThrowError(error);
            }));

      default:
        contentType = 'text/plain';
        return this.httpClient.get(url, { headers: headers, responseType: 'json' })
          .pipe(
            map(response => response),
            tap(response => this.logResponse('getFile', 'getFile()', url, '', '', response)),
            catchError(error => {
              return observableThrowError(error);
            }));
    }

  }

  public logResponse(caller: Object | string, functionName: string, request: any, dataset: any, component: any, response: any) {
    const name = typeof caller === 'string' ? caller : caller.constructor.name;
    window.console.group(name);
    window.console.log(functionName + ' << \'' + dataset + '\' and \'' + component + '\'');
    window.console.log('request:', request);
    window.console.log('response:', response);
    window.console.groupEnd();
  }

  public handleError(caller: Object | string, msg: string, response?: any) {
    const name = typeof caller === 'string' ? caller : caller.constructor.name;
    window.console.group(name);
    window.console.error(msg, response);
    window.console.groupEnd();
  }

  public handleWarning(caller: Object | string, msg: string, warn?: any) {
    const name = typeof caller === 'string' ? caller : caller.constructor.name;
    window.console.group(name);
    window.console.warn(msg, warn);
    window.console.groupEnd();
  }

  public handleInfo(caller: Object | string, msg: string, info?: any) {
    const name = typeof caller === 'string' ? caller : caller.constructor.name;
    window.console.group(name);
    window.console.info(msg, info);
    window.console.groupEnd();
  }

  public handleTrace(caller: Object | string, msg: string, trace?: any) {
    const name = typeof caller === 'string' ? caller : caller.constructor.name;
    window.console.group(name);
    window.console.log(msg, trace);
    window.console.groupEnd();
  }

  override ngOnDestroy() {
    this.destroyed = true;
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.disconnect();
    this.wsMessages$.complete();
    this.connectionState$.complete();
    this.isConnected$.complete();
    super.ngOnDestroy();
  }
}
