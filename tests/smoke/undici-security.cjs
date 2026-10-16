const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, readFileSync, rmSync } = require('node:fs');
const { createServer: createHttpServer } = require('node:http');
const { createServer } = require('node:https');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { Agent, fetch } = require(process.argv[2]);

async function checkEncodingLimit() {
  // GHSA-xjj6-f33q-929c: a rejected response must not crash the process.
  const server = createHttpServer((request, response) => {
    response.writeHead(200, {
      'content-encoding': 'gzip,gzip,gzip,gzip,gzip,gzip',
      'content-length': '1'
    });
    response.flushHeaders();
    response.socket.end();
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    await assert.rejects(fetch(`http://127.0.0.1:${server.address().port}/`, {
      signal: AbortSignal.timeout(10000)
    }), TypeError);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

async function main() {
  await checkEncodingLimit();
  const directory = mkdtempSync(join(tmpdir(), 'undici-tls-smoke-'));
  let server;
  let agent;
  try {
    execFileSync('openssl', [
      'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
      '-keyout', join(directory, 'key.pem'),
      '-out', join(directory, 'cert.pem'), '-days', '1',
      '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'
    ], { stdio: ['ignore', 'ignore', 'pipe'] });
    const certificate = readFileSync(join(directory, 'cert.pem'), 'utf8');
    server = createServer({
      key: readFileSync(join(directory, 'key.pem')),
      cert: certificate
    }, (request, response) => response.end('trusted fixture'));
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');

    // GHSA-2m5v-pch6-74hx: Agent must retain custom TLS verification.
    let verificationCalls = 0;
    agent = new Agent({
      tls: {
        ca: certificate,
        checkServerIdentity() {
          verificationCalls++;
          return new Error('fixture certificate rejected');
        }
      }
    });
    await assert.rejects(fetch(`https://127.0.0.1:${server.address().port}/`, {
      dispatcher: agent,
      signal: AbortSignal.timeout(10000)
    }), error => error.cause?.message === 'fixture certificate rejected');
    assert.ok(verificationCalls > 0);
  } finally {
    if (agent) await agent.close();
    if (server?.listening) await new Promise(resolve => server.close(resolve));
    rmSync(directory, { recursive: true, force: true });
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
