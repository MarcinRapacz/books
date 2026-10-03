// Minimal SMTP sink for local development: accepts every message and prints it. No TLS, no auth.
// Usage: node smtp-sink.mjs [port=2525]
import net from 'node:net';

const port = Number(process.argv[2] ?? 2525);

net.createServer((socket) => {
  let buffer = '';
  let inData = false;
  const reply = (line) => socket.write(`${line}\r\n`);
  reply('220 smtp-sink ready');

  socket.on('data', (chunk) => {
    buffer += chunk.toString('utf8');
    while (true) {
      if (inData) {
        const end = buffer.indexOf('\r\n.\r\n');
        if (end === -1) return;
        console.log(`----- message ${new Date().toISOString()} -----\n${buffer.slice(0, end)}\n----- end -----`);
        buffer = buffer.slice(end + 5);
        inData = false;
        reply('250 OK: queued');
        continue;
      }
      const eol = buffer.indexOf('\r\n');
      if (eol === -1) return;
      const line = buffer.slice(0, eol);
      buffer = buffer.slice(eol + 2);
      const verb = line.slice(0, 4).toUpperCase();
      if (verb === 'EHLO' || verb === 'HELO') reply('250 smtp-sink');
      else if (verb === 'DATA') { inData = true; reply('354 End data with <CR><LF>.<CR><LF>'); }
      else if (verb === 'QUIT') { reply('221 Bye'); socket.end(); return; }
      else reply('250 OK');
    }
  });
}).listen(port, () => console.log(`smtp-sink listening on ${port}`));
