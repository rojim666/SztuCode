export interface ClientTransport {
  send(frame: Uint8Array): void | Promise<void>;
  close(): void | Promise<void>;
}

export interface ClientTransportHandlers {
  onData(chunk: Uint8Array | string): void;
  onClose(): void;
  onError(error: Error): void;
}

export type ClientTransportFactory = (handlers: ClientTransportHandlers) => ClientTransport | Promise<ClientTransport>;
