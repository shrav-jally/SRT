const express = require('express');
const path = require('path');
const http = require('http');
const app = express();
const PORT = process.env.PORT || 3000;

// Parse JSON bodies for POST requests
app.use(express.json({ limit: '50mb' }));

// API proxy middleware - forward all /api/* requests to backend
app.all('/api/*', (req, res) => {
  const bodyData = (req.method !== 'GET' && req.method !== 'HEAD' && req.body) 
    ? JSON.stringify(req.body) : '';
  
  console.log(`[PROXY] ${req.method} ${req.originalUrl} len=${bodyData.length}`);

  const options = {
    hostname: process.env.BACKEND_HOST || 'localhost',
    port: parseInt(process.env.BACKEND_PORT || '5899'),
    path: req.originalUrl,
    method: req.method,
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(bodyData),
      'Accept': 'application/json'
    }
  };

  const proxyReq = http.request(options, (proxyRes) => {
    const chunks = [];
    proxyRes.on('data', chunk => chunks.push(chunk));
    proxyRes.on('end', () => {
      const body = Buffer.concat(chunks);
      console.log(`[PROXY] Response: ${proxyRes.statusCode} len=${body.length}`);
      res.status(proxyRes.statusCode);
      // Forward content-type
      if (proxyRes.headers['content-type']) {
        res.setHeader('Content-Type', proxyRes.headers['content-type']);
      }
      // CORS headers for browser
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
      res.send(body);
    });
  });

  proxyReq.on('error', (err) => {
    console.error('[PROXY] Error:', err.message);
    res.status(502).json({ error: 'Backend proxy error: ' + err.message });
  });

  if (bodyData) {
    proxyReq.write(bodyData);
  }
  proxyReq.end();
});

// Handle CORS preflight
app.options('/api/*', (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.status(204).end();
});

// Proxy FastAPI docs (Swagger UI + ReDoc + OpenAPI schema) through frontend
// so users don't need direct access to port 8000 (which may be blocked by other services)
app.get(['/docs', '/docs/*'], (req, res) => {
  const proxyReq = http.request({
    hostname: process.env.BACKEND_HOST || 'localhost',
    port: parseInt(process.env.BACKEND_PORT || '5899'),
    path: req.originalUrl,
    method: 'GET',
    headers: { 'Accept': 'text/html' }
  }, (proxyRes) => {
    const chunks = [];
    proxyRes.on('data', chunk => chunks.push(chunk));
    proxyRes.on('end', () => {
      res.status(proxyRes.statusCode);
      if (proxyRes.headers['content-type']) res.setHeader('Content-Type', proxyRes.headers['content-type']);
      res.send(Buffer.concat(chunks));
    });
  });
  proxyReq.on('error', (err) => res.status(502).json({ error: 'Backend proxy error: ' + err.message }));
  proxyReq.end();
});

app.get(['/redoc', '/redoc/*'], (req, res) => {
  const proxyReq = http.request({
    hostname: process.env.BACKEND_HOST || 'localhost',
    port: parseInt(process.env.BACKEND_PORT || '5899'),
    path: req.originalUrl,
    method: 'GET',
    headers: { 'Accept': 'text/html' }
  }, (proxyRes) => {
    const chunks = [];
    proxyRes.on('data', chunk => chunks.push(chunk));
    proxyRes.on('end', () => {
      res.status(proxyRes.statusCode);
      if (proxyRes.headers['content-type']) res.setHeader('Content-Type', proxyRes.headers['content-type']);
      res.send(Buffer.concat(chunks));
    });
  });
  proxyReq.on('error', (err) => res.status(502).json({ error: 'Backend proxy error: ' + err.message }));
  proxyReq.end();
});

app.get('/openapi.json', (req, res) => {
  const proxyReq = http.request({
    hostname: process.env.BACKEND_HOST || 'localhost',
    port: parseInt(process.env.BACKEND_PORT || '5899'),
    path: '/openapi.json',
    method: 'GET',
    headers: { 'Accept': 'application/json' }
  }, (proxyRes) => {
    const chunks = [];
    proxyRes.on('data', chunk => chunks.push(chunk));
    proxyRes.on('end', () => {
      res.status(proxyRes.statusCode);
      res.setHeader('Content-Type', 'application/json');
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.send(Buffer.concat(chunks));
    });
  });
  proxyReq.on('error', (err) => res.status(502).json({ error: 'Backend proxy error: ' + err.message }));
  proxyReq.end();
});

// Serve the original Touchless Valuation HTML application with no-cache
app.get('/', (req, res) => {
  res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
  console.log(`E-Vardhan Application running at http://localhost:${PORT}`);
  console.log(`Backend API proxy: /api/* -> http://localhost:5899/api/*`);
});
