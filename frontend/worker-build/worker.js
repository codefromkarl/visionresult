export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    if (request.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });
    if (url.pathname.startsWith('/api/')) {
      const response = await handleAPI(request, env, ctx, url);
      Object.entries(corsHeaders).forEach(([k, v]) => response.headers.set(k, v));
      return response;
    }
    if (url.pathname.startsWith('/images/')) {
      return handleImage(request, env, url);
    }
    return env.ASSETS.fetch(request);
  }
};

async function handleImage(request, env, url) {
  const key = url.pathname.replace('/images/', '');
  const obj = await env.IMAGE_BUCKET.get(key);
  if (!obj) return new Response('Not found', { status: 404 });
  const headers = new Headers();
  headers.set('Content-Type', obj.httpMetadata?.contentType || 'image/jpeg');
  headers.set('Cache-Control', 'public, max-age=86400');
  return new Response(obj.body, { headers });
}

async function handleAPI(request, env, ctx, url) {
  try {
    if (url.pathname === '/api/health') return jr({ status: 'ok' });
    
    if (url.pathname === '/api/history') {
      const limit = parseInt(url.searchParams.get('limit') || '20');
      const offset = parseInt(url.searchParams.get('offset') || '0');
      const results = await env.DB.prepare(
        'SELECT id, status, filename, image_key, created_at, completed_at, result FROM analyses ORDER BY created_at DESC LIMIT ? OFFSET ?'
      ).bind(limit, offset).all();
      const count = await env.DB.prepare('SELECT COUNT(*) as total FROM analyses').first();
      return jr({ items: results.results, total: count.total });
    }
    
    if (url.pathname === '/api/analyze' && request.method === 'POST') {
      const formData = await request.formData();
      const file = formData.get('file');
      if (!file) return jr({ error: 'No file' }, 400);
      const buffer = await file.arrayBuffer();
      const taskId = crypto.randomUUID().slice(0, 8);
      const imageKey = `${taskId}/${file.name}`;
      await env.IMAGE_BUCKET.put(imageKey, buffer, { httpMetadata: { contentType: file.type } });
      await env.DB.prepare(
        'INSERT INTO analyses (id, status, filename, image_key, created_at) VALUES (?, ?, ?, ?, ?)'
      ).bind(taskId, 'processing', file.name, imageKey, new Date().toISOString()).run();
      ctx.waitUntil(processImage(env, taskId, buffer, file.type));
      return jr({ task_id: taskId, status: 'processing' });
    }
    
    if (url.pathname.startsWith('/api/report/')) {
      const taskId = url.pathname.split('/')[3];
      const r = await env.DB.prepare('SELECT * FROM analyses WHERE id = ?').bind(taskId).first();
      if (!r) return jr({ error: 'Not found' }, 404);
      return jr({
        id: r.id, status: r.status, filename: r.filename,
        image_url: r.image_key ? `/images/${r.image_key}` : null,
        created_at: r.created_at, completed_at: r.completed_at,
        analysis: r.result ? JSON.parse(r.result) : null,
      });
    }
    
    if (url.pathname.startsWith('/api/delete/') && request.method === 'DELETE') {
      const taskId = url.pathname.split('/')[3];
      const r = await env.DB.prepare('SELECT image_key FROM analyses WHERE id = ?').bind(taskId).first();
      if (r?.image_key) try { await env.IMAGE_BUCKET.delete(r.image_key); } catch {}
      await env.DB.prepare('DELETE FROM analyses WHERE id = ?').bind(taskId).run();
      return jr({ success: true });
    }
    
    return jr({ error: 'Not found' }, 404);
  } catch (e) {
    return jr({ error: e.message }, 500);
  }
}

function jr(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

async function processImage(env, taskId, imageBuffer, mimeType) {
  try {
    const ai = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...new Uint8Array(imageBuffer)],
      prompt: 'Analyze this image. Respond ONLY with JSON: {"scene_type":"street/indoor/landscape/food/document/other","description":"detailed description","location_guess":{"location":"city","confidence":0.7},"time_guess":{"time_of_day":"morning/afternoon/evening/night","season":"spring/summer/autumn/winter"},"detected_text":["text"],"key_evidence":["evidence"]}',
      max_tokens: 1024,
    });
    const text = ai.description || ai.response || '';
    let result;
    try {
      const m = text.replace(/\\n/g,'\n').replace(/\\"/g,'"').match(/\{[\s\S]*\}/);
      result = m ? JSON.parse(m[0]) : { description: text.substring(0, 500) };
    } catch { result = { description: text.substring(0, 500) }; }
    result.scene_type = result.scene_type || 'unknown';
    result.detected_text = result.detected_text || [];
    result.key_evidence = result.key_evidence || [];
    await env.DB.prepare('UPDATE analyses SET status=?, result=?, completed_at=? WHERE id=?')
      .bind('completed', JSON.stringify(result), new Date().toISOString(), taskId).run();
  } catch (e) {
    await env.DB.prepare('UPDATE analyses SET status=?, error=? WHERE id=?')
      .bind('failed', e.message, taskId).run();
  }
}
