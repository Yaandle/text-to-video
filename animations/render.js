#!/usr/bin/env node
/**
 * render.js
 * ---------
 * Headless Puppeteer renderer. Called by animation_visualiser.py as:
 *
 *   node render.js <payload_json_path>
 *
 * Workflow:
 *   1. Read the JSON payload written by animation_visualiser.py.
 *   2. Spin up a local Vite dev server (or use a pre-built dist/).
 *   3. Open a Puppeteer page, inject window.__RENDER_PAYLOAD__, load the app.
 *   4. Screenshot frames at 30fps until window.__ANIMATION_COMPLETE__ is true
 *      OR the max duration is reached.
 *   5. Write frames as frame_0001.png, frame_0002.png ... into framesDir.
 *   6. Exit 0 on success, 1 on failure.
 *
 * Dependencies (installed via npm):
 *   puppeteer, vite (as dev server)
 */

const puppeteer  = require('puppeteer');
const { spawn }  = require('child_process');
const fs         = require('fs');
const path       = require('path');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const FPS           = 30;
const STARTUP_DELAY = 2000; // ms to wait after Vite is confirmed ready

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getRandomPort() {
  return Math.floor(Math.random() * (65000 - 49152 + 1)) + 49152;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function zeroPad(n, digits = 4) {
  return String(n).padStart(digits, '0');
}

function waitForVite(port, maxWaitMs = 20000) {
  const http  = require('http');
  const start = Date.now();

  return new Promise(async (resolve) => {
    while (Date.now() - start < maxWaitMs) {
      try {
        await new Promise((ok, fail) => {
          const req = http.get(`http://localhost:${port}`, res => ok(res.statusCode));
          req.on('error', fail);
          req.setTimeout(600, () => { req.destroy(); fail(new Error('timeout')); });
        });
        return resolve(true);
      } catch {
        await sleep(300);
      }
    }
    resolve(false);
  });
}

/**
 * Spawn Vite and resolve with the port it actually bound to.
 *
 * Key Windows fix: always use shell:true so that `npx` resolves correctly
 * through cmd.exe on Windows. On POSIX this is a no-op.
 */
function spawnVite(requestedPort) {
  return new Promise((resolve, reject) => {
    // On Windows, npx must run through the shell to be found.
    const isWin = process.platform === 'win32';
    const cmd   = isWin ? 'npx.cmd' : 'npx';

    const vite = spawn(
      cmd,
      ['vite', '--port', String(requestedPort)],
      {
        // cwd = animations directory so Vite serves the right project
        cwd:   __dirname,
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: isWin,   // needed on Windows for npx.cmd resolution
      }
    );

    let resolvedPort = null;

    const onData = (chunk) => {
      const text = chunk.toString();
      process.stdout.write(`[vite] ${text}`); // echo Vite output for debugging

      const match = text.match(/localhost:(\d+)/);
      if (match && !resolvedPort) {
        resolvedPort = Number(match[1]);
        console.log(`[render.js] Vite bound to port ${resolvedPort}`);
        resolve({ vite, port: resolvedPort });
      }
    };

    vite.stdout.on('data', onData);
    vite.stderr.on('data', onData); // Vite ≥5 prints to stderr on Windows

    vite.on('error', (err) => {
      console.error(`[render.js] Failed to spawn Vite: ${err.message}`);
      reject(err);
    });

    vite.on('exit', (code) => {
      if (!resolvedPort) {
        reject(new Error(`Vite exited with code ${code} before announcing port`));
      }
    });

    // Fallback: if no port seen within 12 s, assume requestedPort was used
    setTimeout(() => {
      if (!resolvedPort) {
        console.warn('[render.js] No port announcement from Vite; assuming requested port.');
        resolvedPort = requestedPort;
        resolve({ vite, port: requestedPort });
      }
    }, 12_000);
  });
}

// ---------------------------------------------------------------------------
// Cleanup registry
// ---------------------------------------------------------------------------

let _viteProc = null;
let _browser  = null;

function registerCleanup() {
  const cleanup = () => {
    if (_browser)  { try { _browser.close(); } catch {} }
    if (_viteProc) { try { _viteProc.kill(); } catch {} }
  };
  process.on('exit',    cleanup);
  process.on('SIGINT',  () => { cleanup(); process.exit(130); });
  process.on('SIGTERM', () => { cleanup(); process.exit(143); });
  process.on('uncaughtException', (err) => {
    console.error('[render.js] Uncaught exception:', err);
    cleanup();
    process.exit(1);
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  registerCleanup();

  const payloadPath = process.argv[2];
  if (!payloadPath) {
    console.error('Usage: node render.js <payload_json_path>');
    process.exit(1);
  }

  // 1. Load payload -----------------------------------------------------------
  let payload;
  try {
    payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
  } catch (e) {
    console.error(`[render.js] Failed to read payload: ${e.message}`);
    process.exit(1);
  }

  const { componentId, data, width, height, durationSeconds } = payload;

  // CRITICAL: resolve framesDir to an absolute path.
  // Python always sends an absolute path, but guard against edge cases.
  const framesDir   = path.resolve(payload.framesDir);
  const totalFrames = Math.ceil(durationSeconds * FPS);

  console.log(`[render.js] Component  : ${componentId}`);
  console.log(`[render.js] Dimensions : ${width}x${height}`);
  console.log(`[render.js] Duration   : ${durationSeconds}s (${totalFrames} frames @ ${FPS}fps)`);
  console.log(`[render.js] Output dir : ${framesDir}`);   // <-- absolute path logged

  // 2. Prepare output directory ----------------------------------------------
  // Clear stale PNGs so frame count validation is accurate.
  if (fs.existsSync(framesDir)) {
    fs.readdirSync(framesDir)
      .filter(f => f.endsWith('.png'))
      .forEach(f => fs.unlinkSync(path.join(framesDir, f)));
  } else {
    fs.mkdirSync(framesDir, { recursive: true });
  }

  // 3. Start Vite ------------------------------------------------------------
  const requestedPort = getRandomPort();
  console.log(`[render.js] Requesting Vite on port ${requestedPort}...`);

  const { vite, port: vitePort } = await spawnVite(requestedPort);
  _viteProc = vite;

  console.log(`[render.js] Polling Vite on port ${vitePort}...`);
  const ready = await waitForVite(vitePort);
  if (!ready) {
    console.error('[render.js] Vite server failed to start in time.');
    vite.kill();
    process.exit(1);
  }
  console.log('[render.js] Vite ready — waiting for React hydration...');
  await sleep(STARTUP_DELAY);

  // 4. Launch Puppeteer ------------------------------------------------------
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-gpu',
      `--window-size=${width},${height}`,
    ],
  });
  _browser = browser;

  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });

  // Inject render payload before the app loads so the React component can
  // read it from window.__RENDER_PAYLOAD__ during its first render.
  await page.evaluateOnNewDocument((p) => {
    window.__RENDER_PAYLOAD__     = p;
    window.__ANIMATION_COMPLETE__ = false;
  }, payload);

  await page.goto(`http://localhost:${vitePort}`, { waitUntil: 'networkidle0', timeout: 30000 });

  // Let React finish its initial render cycle
  await sleep(300);
  // Inject theme background before capturing frames
  await page.evaluate((themeColor) => {
    // 1. Set body background so full viewport is filled
    document.body.style.background = themeColor;

    // 2. If your React root div exists, fill it too
    const rootDiv = document.getElementById('root'); // adjust ID if different
    if (rootDiv) {
      rootDiv.style.background = themeColor;
    }

    // 3. Optional: propagate background to canvas elements inside the graph
    const canvases = document.querySelectorAll('canvas');
    canvases.forEach(c => {
      const ctx = c.getContext('2d');
      if (ctx) {
        ctx.save();
        ctx.globalCompositeOperation = 'destination-over';
        ctx.fillStyle = themeColor;
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.restore();
      }
    });

  }, payload.theme?.backgroundColor || '#ffffff'); // fallback white
  // 5. Capture frames --------------------------------------------------------
  console.log(`[render.js] Capturing ${totalFrames} frames...`);

  const frameInterval = 1000 / FPS;

  for (let frameIndex = 0; frameIndex < totalFrames; frameIndex++) {
    const framePath = path.join(framesDir, `frame_${zeroPad(frameIndex + 1)}.png`);

    await page.screenshot({
      path: framePath,
      type: 'png',
      clip: { x: 0, y: 0, width, height },
    });

    // Check if the React component signalled early completion
    const done = await page.evaluate(() => window.__ANIMATION_COMPLETE__ === true);
    if (done && frameIndex >= FPS) {
      console.log(`[render.js] Animation signalled complete at frame ${frameIndex + 1}. Holding last frame.`);
      const lastFrame = fs.readFileSync(framePath);
      for (let i = frameIndex + 1; i < totalFrames; i++) {
        fs.writeFileSync(path.join(framesDir, `frame_${zeroPad(i + 1)}.png`), lastFrame);
      }
      break;
    }

    await sleep(frameInterval);

    if ((frameIndex + 1) % 30 === 0) {
      console.log(`[render.js] Frame ${frameIndex + 1}/${totalFrames}`);
    }
  }

  // 6. Validate output -------------------------------------------------------
  const written = fs.readdirSync(framesDir).filter(f => f.endsWith('.png')).length;
  if (written === 0) {
    console.error(`[render.js] ✗ No frames were written to ${framesDir}`);
    await browser.close();
    vite.kill();
    process.exit(1);
  }

  console.log(`[render.js] ✓ ${written} frames written to ${framesDir}`);

  // 7. Cleanup ---------------------------------------------------------------
  await browser.close();
  _browser = null;

  vite.kill();
  _viteProc = null;

  process.exit(0);
}

main().catch(err => {
  console.error('[render.js] Fatal error:', err);
  process.exit(1);
});