export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }
    
    if (url.pathname.startsWith('/api/')) {
      const response = await handleAPI(request, env, ctx, url);
      Object.entries(corsHeaders).forEach(([key, value]) => {
        response.headers.set(key, value);
      });
      return response;
    }
    
    return env.ASSETS.fetch(request);
  }
};

async function handleAPI(request, env, ctx, url) {
  try {
    // Health
    if (url.pathname === '/api/health') {
      return jsonResponse({ status: 'ok', service: 'vision-insight' });
    }
    
    // 历史记录列表
    if (url.pathname === '/api/history' && request.method === 'GET') {
      const limit = parseInt(url.searchParams.get('limit') || '20');
      const offset = parseInt(url.searchParams.get('offset') || '0');
      
      const results = await env.DB.prepare(
        'SELECT id, status, filename, created_at, completed_at FROM analyses ORDER BY created_at DESC LIMIT ? OFFSET ?'
      ).bind(limit, offset).all();
      
      const count = await env.DB.prepare('SELECT COUNT(*) as total FROM analyses').first();
      
      return jsonResponse({
        items: results.results,
        total: count.total,
        limit,
        offset,
      });
    }
    
    // 上传分析
    if (url.pathname === '/api/analyze' && request.method === 'POST') {
      const formData = await request.formData();
      const file = formData.get('file');
      
      if (!file) {
        return jsonResponse({ error: 'No file uploaded' }, 400);
      }
      
      const buffer = await file.arrayBuffer();
      const taskId = crypto.randomUUID().slice(0, 8);
      
      await env.IMAGE_BUCKET.put(`${taskId}/${file.name}`, buffer, {
        httpMetadata: { contentType: file.type },
      });
      
      await env.DB.prepare(
        'INSERT INTO analyses (id, status, filename, created_at) VALUES (?, ?, ?, ?)'
      ).bind(taskId, 'processing', file.name, new Date().toISOString()).run();
      
      ctx.waitUntil(processImage(env, taskId, buffer, file.type));
      
      return jsonResponse({
        task_id: taskId,
        status: 'processing',
        message: 'Analysis started.'
      });
    }
    
    // 查询结果
    if (url.pathname.startsWith('/api/report/')) {
      const taskId = url.pathname.split('/api/report/')[1];
      
      const result = await env.DB.prepare(
        'SELECT * FROM analyses WHERE id = ?'
      ).bind(taskId).first();
      
      if (!result) {
        return jsonResponse({ error: 'Task not found' }, 404);
      }
      
      return jsonResponse({
        id: result.id,
        status: result.status,
        filename: result.filename,
        created_at: result.created_at,
        completed_at: result.completed_at,
        analysis: result.result ? JSON.parse(result.result) : null,
        error: result.error,
      });
    }
    
    // 删除记录
    if (url.pathname.startsWith('/api/delete/') && request.method === 'DELETE') {
      const taskId = url.pathname.split('/api/delete/')[1];
      
      await env.DB.prepare('DELETE FROM analyses WHERE id = ?').bind(taskId).run();
      try {
        await env.IMAGE_BUCKET.delete(`${taskId}/`);
      } catch {}
      
      return jsonResponse({ success: true });
    }
    
    return jsonResponse({ error: 'Not found' }, 404);
    
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

async function processImage(env, taskId, imageBuffer, mimeType) {
  try {
    const aiResponse = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...new Uint8Array(imageBuffer)],
      prompt: `Analyze this image. Respond ONLY with valid JSON:
{
  "scene_type": "street/indoor/landscape/food/document/other",
  "description": "detailed description",
  "location_guess": {"location": "city or place", "confidence": 0.7},
  "time_guess": {"time_of_day": "morning/afternoon/evening/night", "season": "spring/summer/autumn/winter"},
  "detected_text": ["text in image"],
  "key_evidence": ["key visual evidence"]
}`,
      max_tokens: 1024,
    });
    
    const responseText = aiResponse.description || aiResponse.response || '';
    
    let result;
    try {
      let cleanText = responseText.replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\_/g, '_');
      const jsonMatch = cleanText.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        result = JSON.parse(jsonMatch[0]);
        result.scene_type = result.scene_type || 'unknown';
        result.description = result.description || '';
        result.detected_text = result.detected_text || [];
        result.key_evidence = result.key_evidence || [];
      } else {
        throw new Error('No JSON found');
      }
    } catch (e) {
      result = {
        scene_type: 'unknown',
        description: responseText.substring(0, 500),
        location_guess: null,
        time_guess: null,
        detected_text: [],
        key_evidence: []
      };
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
