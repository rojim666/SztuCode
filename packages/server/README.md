# TypeScript server layer

`@sztucode/server` owns the TCP/NDJSON transport, connection lifecycle,
optional protocol handshake, JSON-RPC routing and live session attachment.
It accepts a `PiSessionRuntime`/`SessionRuntime` service boundary; it never
constructs an `AgentLoop`.

The new `Server` defaults to a version-1 `hello` handshake. Set
`requireHandshake: false` for a legacy JSON-RPC peer. The runtime daemon uses
the transport's compatibility mode so existing desktop and CLI clients can
continue sending their first JSON-RPC frame directly on port 7438.

Live runtimes are reference-counted by attached connections. Disconnecting a
client detaches it, but an active runtime remains alive until it becomes idle;
operations overlap-protect with a typed busy error. `close()` stops accepting
connections, detaches clients, disposes live runtimes and is idempotent.
