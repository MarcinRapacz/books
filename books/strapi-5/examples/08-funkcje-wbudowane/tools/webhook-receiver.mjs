// Tiny webhook receiver: verifies the shared secret header and prints the event.
// Usage: WEBHOOK_SECRET=... node webhook-receiver.mjs [port=4008]
import http from 'node:http';
import { timingSafeEqual } from 'node:crypto';

const port = Number(process.argv[2] ?? 4008);
const secret = Buffer.from(process.env.WEBHOOK_SECRET ?? '');

const isAuthorized = (header) => {
  const given = Buffer.from(header ?? '');
  return secret.length > 0 && given.length === secret.length && timingSafeEqual(given, secret);
};

http.createServer((req, res) => {
  let body = '';
  req.on('data', (chunk) => (body += chunk));
  req.on('end', () => {
    if (!isAuthorized(req.headers['x-webhook-secret'])) {
      console.log(`401 rejected ${req.headers['x-strapi-event'] ?? '-'}`);
      res.writeHead(401).end();
      return;
    }
    const { event, uid, entry } = JSON.parse(body);
    console.log(`200 ${event} ${uid} ${entry?.documentId} locale=${entry?.locale} slug=${entry?.slug}`);
    console.log(JSON.stringify({ headers: req.headers, body: JSON.parse(body) }));
    res.writeHead(200, { 'content-type': 'application/json' }).end('{"revalidated":true}');
  });
}).listen(port, () => console.log(`webhook-receiver listening on ${port}`));
