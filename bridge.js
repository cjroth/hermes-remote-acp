#!/usr/bin/env node
'use strict';
// Minimal stdio <-> WebSocket bridge for hermes-acp, with optional TLS.
//
// Why custom instead of stdio-to-ws: `tailscale serve --https` (TLS terminated
// in tailscaled's userspace netstack) wedges after ~1 connection on Railway.
// Raw TCP passthrough (`serve --tcp`) is fast and stable, so we terminate TLS
// HERE and let Tailscale just forward bytes. Framing matches stdio-to-ws's
// "line" mode: one stdout line == one WS message; each WS message is written to
// stdin newline-terminated (hermes-acp parses stdin with readline()).
//
// Env:
//   BRIDGE_PORT  port to listen on            (default 8443)
//   WS_HOST      bind address                 (default 127.0.0.1 — loopback)
//   TLS_CERT     cert file (PEM) -> serve WSS  (omit both -> plain WS)
//   TLS_KEY      key file  (PEM)
//   ACP_CMD      agent command                (default hermes-acp)

const { spawn } = require('child_process');
const readline = require('readline');
const { WebSocketServer } = require('ws');

const PORT = parseInt(process.env.BRIDGE_PORT || '8443', 10);
const HOST = process.env.WS_HOST || '127.0.0.1';
const CMD  = process.env.ACP_CMD || 'hermes-acp';
const { TLS_CERT, TLS_KEY } = process.env;

let wss;
if (TLS_CERT && TLS_KEY) {
  const fs = require('fs');
  const https = require('https');
  const server = https.createServer({
    cert: fs.readFileSync(TLS_CERT),
    key: fs.readFileSync(TLS_KEY),
  });
  server.listen(PORT, HOST, () =>
    console.error(`[bridge] WSS (TLS) listening on ${HOST}:${PORT}`));
  wss = new WebSocketServer({ server });
} else {
  wss = new WebSocketServer({ host: HOST, port: PORT });
  console.error(`[bridge] WS (plaintext) listening on ${HOST}:${PORT}`);
}

wss.on('connection', (ws) => {
  const child = spawn(CMD, { stdio: ['pipe', 'pipe', 'inherit'] });
  const rl = readline.createInterface({ input: child.stdout });

  rl.on('line', (line) => {
    if (line.length && ws.readyState === ws.OPEN) ws.send(line);
  });
  ws.on('message', (data) => {
    const msg = data.toString();
    if (child.stdin.writable) child.stdin.write(msg.endsWith('\n') ? msg : msg + '\n');
  });

  const cleanup = () => { try { child.kill('SIGTERM'); } catch {} };
  ws.on('close', cleanup);
  ws.on('error', cleanup);
  child.on('exit', () => { try { ws.close(); } catch {} });
  child.on('error', () => { try { ws.close(); } catch {} });
});

console.error('[bridge] ready');
