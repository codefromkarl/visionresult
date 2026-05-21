export function onRequestGet() {
  return new Response(JSON.stringify({ status: 'ok', message: 'Functions are working!' }), {
    headers: { 'Content-Type': 'application/json' }
  });
}

export function onRequestPost() {
  return new Response(JSON.stringify({ status: 'ok', method: 'POST' }), {
    headers: { 'Content-Type': 'application/json' }
  });
}
