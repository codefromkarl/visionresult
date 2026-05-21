export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }
    
    // API routes
    if (url.pathname.startsWith('/api/')) {
      const response = await handleAPI(request, env, ctx, url);
      // Add CORS headers to response
      Object.entries(corsHeaders).forEach(([key, value]) => {
        response.headers.set(key, value);
      });
      return response;
    }
    
    // Serve static files
    return env.ASSETS.fetch(request);
  }
};

async function handleAPI(request, env, ctx, url) {
  try {
    // Health check
    if (url.pathname === '/api/health') {
      return new Response(JSON.stringify({ status: 'ok', service: 'vision-insight' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    // Image analysis
    if (url.pathname === '/api/analyze' && request.method === 'POST') {
      const formData = await request.formData();
      const file = formData.get('file');
      
      if (!file) {
        return new Response(JSON.stringify({ error: 'No file uploaded' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      
      const buffer = await file.arrayBuffer();
      const taskId = crypto.randomUUID().slice(0, 8);
      
      // Upload to R2
      await env.IMAGE_BUCKET.put(`${taskId}/${file.name}`, buffer, {
        httpMetadata: { contentType: file.type },
      });
      
      // Create DB record
      await env.DB.prepare(
        'INSERT INTO analyses (id, status, filename, created_at) VALUES (?, ?, ?, ?)'
      ).bind(taskId, 'processing', file.name, new Date().toISOString()).run();
      
      // Process with AI (async) - use ctx.waitUntil instead of request.waitUntil
      ctx.waitUntil(processImage(env, taskId, buffer, file.type));
      
      return new Response(JSON.stringify({
        task_id: taskId,
        status: 'processing',
        message: 'Analysis started. Poll /api/report/{task_id} for results.'
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    // Report endpoint
    if (url.pathname.startsWith('/api/report/')) {
      const taskId = url.pathname.split('/api/report/')[1];
      
      const result = await env.DB.prepare(
        'SELECT * FROM analyses WHERE id = ?'
      ).bind(taskId).first();
      
      if (!result) {
        return new Response(JSON.stringify({ error: 'Task not found' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      
      const analysis = result.result ? JSON.parse(result.result) : null;
      
      return new Response(JSON.stringify({
        id: result.id,
        status: result.status,
        filename: result.filename,
        created_at: result.created_at,
        completed_at: result.completed_at,
        analysis: analysis,
        error: result.error,
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    return new Response(JSON.stringify({ error: 'Not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function processImage(env, taskId, imageBuffer, mimeType) {
  try {
    const analysis = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...new Uint8Array(imageBuffer)],
      prompt: `Analyze this image and respond in JSON format:
{
  "scene_type": "type of scene",
  "description": "detailed description",
  "location_guess": {"location": "possible location", "confidence": 0.0-1.0},
  "time_guess": {"time_of_day": "time", "season": "season"},
  "detected_text": ["text in image"],
  "key_evidence": ["key evidence"]
}`,
      max_tokens: 1024,
    });
    
    let result;
    try {
      const jsonMatch = analysis.response.match(/\{[\s\S]*\}/);
      result = jsonMatch ? JSON.parse(jsonMatch[0]) : { description: analysis.response };
    } catch {
      result = { description: analysis.response };
    }
    
    await env.DB.prepare(
      'UPDATE analyses SET status = ?, result = ?, completed_at = ? WHERE id = ?'
    ).bind('completed', JSON.stringify(result), new Date().toISOString(), taskId).run();
    
  } catch (error) {
    await env.DB.prepare(
      'UPDATE analyses SET status = ?, error = ? WHERE id = ?'
    ).bind('failed', error.message, taskId).run();
  }
}
