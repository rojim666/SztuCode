# `@sztucode/client`

Transport-neutral TypeScript SDK for the SztuCode daemon. The SDK only sends
typed JSON-RPC requests to daemon endpoints; it does not import or invoke
tools, providers, or `AgentLoop` code.

```ts
import { DaemonClient } from "@sztucode/client";
import { createTcpTransportFactory } from "@sztucode/client/tcp";

const client = await DaemonClient.connect({
  transportFactory: createTcpTransportFactory({ host: "127.0.0.1", port: 7438 }),
  requestTimeoutMs: 20_000,
});
const session = await client.createSession({ name: "review" }, { idempotencyKey: "create-review-1" });
await client.prompt(session.session_id, "Inspect the project");
const unsubscribe = client.subscribeEvents({ topics: ["run.*"] }, (event) => console.log(event.type));
unsubscribe();
await client.close();
```

`reconnect()` creates a fresh transport and repeats the hello handshake. Every
request has a generated or caller-supplied id, optional idempotency key, and
timeout. Disconnects reject pending requests with `ClientDisconnectedError`;
malformed frames and invalid response ordering use `ClientProtocolError`.

Desktop/Tauri callers can provide a bridge-backed `ClientTransportFactory`;
CLI/Node callers can use the TCP adapter from `@sztucode/client/tcp`.
