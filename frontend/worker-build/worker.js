export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
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
    if (url.pathname === '/api/health') {
      return jsonResponse({ status: 'ok', service: 'vision-insight' });
    }
    
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
      prompt: `Analyze this image. Respond ONLY with valid JSON, no other text:
{
  "scene_type": "street/indoor/landscape/food/document/other",
  "description": "detailed description of what you see",
  "location_guess": {"location": "city or place name", "confidence": 0.7},
  "time_guess": {"time_of_day": "morning/afternoon/evening/night", "season": "spring/summer/autumn/winter"},
  "detected_text": ["any text visible in the image"],
  "key_evidence": ["key visual evidence you used for your analysis"]
}`,
      max_tokens: 1024,
    });
    
    const responseText = aiResponse.description || aiResponse.response || '';
    
    let result;
    try {
      // 清理响应文本，移除转义字符
      let cleanText = responseText
        .replace(/\\n/g, '\n')
        .replace(/\\"/g, '"')
        .replace(/\\_/g, '_');
      
      // 提取 JSON
      const jsonMatch = cleanText.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        result = JSON.parse(jsonMatch[0]);
        result.scene_type = result.scene_type || 'unknown';
        result.description = result.description || '';
        result.detected_text = result.detected_text || [];
        result.key_evidence = result.key_evidence || [];
        if (result.location_guess && typeof result.location_guess.confidence !== 'number') {
          result.location_guess.confidence = parseFloat(result.location_guess.confidence) || 0.5;
        }
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
