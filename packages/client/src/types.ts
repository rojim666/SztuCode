import type {
  ClientHello, EventEnvelope, EventSubscribeParams, EventSubscribeResult, IdempotencyKey, JsonRpcResponse,
  PongResult, RequestId, RuntimeEvent, ServerHello, SessionCommandCreate, SessionCommandResult, SessionSnapshot,
} from "@sztucode/protocol";
import type { ClientTransportFactory } from "./transport.js";

export type ConnectionState = "disconnected" | "connecting" | "connected" | "closed";
export type Unsubscribe = () => void;
export interface ConnectionStateChange { state: ConnectionState; error?: Error }
export interface RequestOptions { timeoutMs?: number; requestId?: RequestId; idempotencyKey?: IdempotencyKey }
export interface DaemonClientOptions {
  transportFactory: ClientTransportFactory;
  clientName?: string;
  capabilities?: ClientHello["capabilities"];
  requestTimeoutMs?: number;
  handshakeTimeoutMs?: number;
  maxFrameBytes?: number;
  onListenerError?: (error: Error) => void;
}
export type EventListener = (event: RuntimeEvent) => void;
export interface EventSubscriptionOptions extends Omit<EventSubscribeParams, "type"> {}
export interface DaemonClientSnapshot { hello: ServerHello; lastEvent?: RuntimeEvent }
export type { EventEnvelope, EventSubscribeResult, JsonRpcResponse, PongResult, RequestId, SessionCommandCreate, SessionCommandResult, SessionSnapshot };
