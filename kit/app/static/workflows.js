/* ComfyUI Lite Studio: Guided modular recipes, intelligent auto-recommendations, interactive LoRA stacks, and image lanes. */
const COMFY_LITE_ARCHITECTURES = {
  sdxl: {
    id: 'sdxl',
    name: 'SDXL / Pony / Illustrious',
    description: 'Premier anime, illustration, and high-fidelity general diffusion.',
    family: 'sdxl',
    recommended: {
      checkpoint: 'animagineXLV3_v30.safetensors',
      vae: 'sdxl_vae.safetensors',
      clip: 'Built-in SDXL CLIP',
      clip_skip: -2,
      width: 832,
      height: 1216,
      steps: 24,
      cfg: 5.5,
      sampler: 'euler_ancestral',
      scheduler: 'normal',
      quality: 'masterpiece, best quality, highly detailed, score_9, score_8_up',
      negative: 'low quality, worst quality, blurry, bad anatomy, bad hands, extra limbs'
    },
    defaultLane: 'portrait'
  },
  flux: {
    id: 'flux',
    name: 'Flux.1 (Dev / Schnell)',
    description: 'Next-gen flow transformer with state-of-the-art anatomy and lighting.',
    family: 'zimage',
    recommended: {
      checkpoint: 'flux1-schnell.safetensors',
      vae: 'ae.safetensors',
      clip: 't5xxl_fp16.safetensors',
      clip_skip: -1,
      width: 1024,
      height: 1024,
      steps: 8,
      cfg: 1.0,
      sampler: 'euler',
      scheduler: 'simple',
      quality: 'cinematic lighting, ultra detailed, photorealistic 8k, award winning, hyperrealistic',
      negative: 'blurry, artificial, cartoon, distorted, noisy, oversaturated'
    },
    defaultLane: 'realistic'
  },
  sd15: {
    id: 'sd15',
    name: 'Stable Diffusion 1.5',
    description: 'Lightweight, ultra-fast generation with huge LoRA ecosystem.',
    family: 'sd15',
    recommended: {
      checkpoint: 'v1-5-pruned-emaonly.safetensors',
      vae: 'vae-ft-mse-840000-ema-pruned.safetensors',
      clip: 'Built-in SD 1.5 CLIP',
      clip_skip: -1,
      width: 512,
      height: 768,
      steps: 22,
      cfg: 7.0,
      sampler: 'dpmpp_2m_karras',
      scheduler: 'karras',
      quality: 'masterpiece, best quality, sharp focus, 8k uhd, photorealistic, intricate details',
      negative: 'lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit'
    },
    defaultLane: 'casual'
  },
  zimage: {
    id: 'zimage',
    name: 'Z-Image / Lumina / Krea',
    description: 'High-speed diffusion with AuraFlow sampling and Lumina text encoders.',
    family: 'zimage',
    recommended: {
      checkpoint: 'lumina-2-model.safetensors',
      vae: 'ae.safetensors',
      clip: 'lumina-2-clip.safetensors',
      clip_skip: -1,
      width: 1024,
      height: 1024,
      steps: 12,
      cfg: 3.5,
      sampler: 'dpmpp_2m_sde',
      scheduler: 'beta',
      quality: 'high quality, masterpiece, vivid colors, crisp focus',
      negative: 'blurry, low quality, artifacts'
    },
    defaultLane: 'anime'
  }
};

const LANES = [
  ['portrait', '👤 Portrait', 'lane-portrait', 'Character portraits and closeups'],
  ['anime', '🎨 Anime', 'lane-anime', 'Stylized anime & illustration'],
  ['realistic', '📸 Realistic', 'lane-realistic', 'Photorealistic captures'],
  ['scenery', '🌿 Scenery', 'lane-scenery', 'Landscapes & environments (excludes companion identity)'],
  ['casual', '👗 Casual', 'lane-portrait', 'Daily companion moments'],
  ['default', '🌟 Default Fallback', '', 'General fallback preset']
];

function buildModularWorkflowGraph(draft) {
  const promptNodes = { quality: '101', identity: '102', wardrobe: '103', scene: '104', lighting: '105', camera: '106' };
  const graph = {
    '1': { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: draft.checkpoint || 'CHOOSE_YOUR_CHECKPOINT.safetensors' } },
    '8': { class_type: 'CLIPSetLastLayer', inputs: { clip: ['1', 1], stop_at_clip_layer: Number(draft.clip_skip || -2) } },
    '201': { class_type: 'CLIPTextEncode', inputs: { clip: ['8', 0], text: draft.negative || '' } },
    '301': { class_type: 'EmptyLatentImage', inputs: { width: Number(draft.width || 832), height: Number(draft.height || 1216), batch_size: 1 } },
    '302': { class_type: 'KSampler', inputs: { model: ['1', 0], positive: ['115', 0], negative: ['201', 0], latent_image: ['301', 0], seed: 0, steps: Number(draft.steps || 22), cfg: Number(draft.cfg || 5.5), sampler_name: draft.sampler || 'euler_ancestral', scheduler: draft.scheduler || 'normal', denoise: 1.0 } },
    '303': { class_type: 'VAEDecode', inputs: { samples: ['302', 0], vae: ['1', 2] } },
    '304': { class_type: 'SaveImage', inputs: { images: ['303', 0], filename_prefix: 'Companion' } }
  };

  let modelRef = ['1', 0], clipRef = ['8', 0];

  // Insert LoRA stack
  const enabledLoras = (draft.loras || []).filter(l => l.enabled !== false && l.filename);
  enabledLoras.forEach((lora, idx) => {
    const nodeId = String(500 + idx);
    graph[nodeId] = {
      class_type: 'LoraLoader',
      inputs: {
        model: modelRef,
        clip: clipRef,
        lora_name: lora.filename,
        strength_model: Number(lora.strength_model ?? 1.0),
        strength_clip: Number(lora.strength_clip ?? 1.0)
      }
    };
    modelRef = [nodeId, 0];
    clipRef = [nodeId, 1];
  });

  // Prompt conditioning nodes
  for (const node of Object.values(promptNodes)) {
    graph[node] = { class_type: 'CLIPTextEncode', inputs: { clip: clipRef, text: '' } };
  }
  graph['201'].inputs.clip = clipRef;
  graph['302'].inputs.model = modelRef;

  // Conditioning concatenation chain
  const order = ['102', '103', '104', '105', '106'];
  order.forEach((node, index) => {
    graph[String(111 + index)] = {
      class_type: 'ConditioningConcat',
      inputs: {
        conditioning_to: [index === 0 ? '101' : String(110 + index), 0],
        conditioning_from: [node, 0]
      }
    };
  });

  const mappings = {
    ...Object.fromEntries(Object.entries(promptNodes).map(([k, v]) => [k, [v, 'text']])),
    negative: ['201', 'text'],
    width: ['301', 'width'],
    height: ['301', 'height'],
    seed: ['302', 'seed'],
    steps: ['302', 'steps'],
    cfg: ['302', 'cfg']
  };

  return { graph, mappings };
}

async function renderWorkflowCreator(container, onCreate) {
  const data = await api('/workflows');
  let config = data.settings, library = [], inspected = null;
  /* A model's own terms travel with the weights, not with this kit. Civitai
     publishes four permission flags per model; show them before downloading,
     and say plainly that they summarise rather than replace the model card. */
  const licenceNotice = (licence, page) => {
    if (!licence) return '';
    const rows = [['allowCommercialUse', 'Commercial use'], ['allowDerivatives', 'Derivatives'],
                  ['allowNoCredit', 'Use without credit'], ['allowDifferentLicense', 'Relicensing']];
    const read = v => Array.isArray(v) ? (v.length ? v.join(', ') : 'None') :
                      v === true ? 'Allowed' : v === false ? 'Not allowed' : 'Not stated';
    const restricted = v => v === false || (Array.isArray(v) && !v.length);
    const strict = rows.some(([k]) => restricted(licence[k]));
    return `<div class="card licence-note${strict ? ' is-restricted' : ''}">
      <strong>The publisher's terms for these weights</strong>
      <dl>${rows.map(([k, label]) => `<div><dt>${esc(label)}</dt><dd${restricted(licence[k]) ? ' class="bad"' : ''}>${esc(read(licence[k]))}</dd></div>`).join('')}</dl>
      <p class="dim small">A summary published by Civitai, not the licence itself.${page ? ' Read the <a href="' + esc(page) + '" target="_blank" rel="noopener noreferrer">model card</a> before relying on it.' : ''} These terms bind your use of the weights regardless of Companion Kit's own licence.</p>
    </div>`;
  };

  let selectedArchKey = 'sdxl';
  let initialArch = COMFY_LITE_ARCHITECTURES[selectedArchKey];

  let draft = {
    name: 'Comfy – ' + initialArch.name.split('/')[0].trim(),
    archKey: selectedArchKey,
    family: initialArch.family,
    lane: initialArch.defaultLane,
    checkpoint: initialArch.recommended.checkpoint,
    vae: initialArch.recommended.vae,
    clip: initialArch.recommended.clip,
    clip_skip: initialArch.recommended.clip_skip,
    width: initialArch.recommended.width,
    height: initialArch.recommended.height,
    steps: initialArch.recommended.steps,
    cfg: initialArch.recommended.cfg,
    sampler: initialArch.recommended.sampler,
    scheduler: initialArch.recommended.scheduler,
    quality: initialArch.recommended.quality,
    negative: initialArch.recommended.negative,
    loras: []
  };

  function selectArchitecture(key) {
    selectedArchKey = key;
    const arch = COMFY_LITE_ARCHITECTURES[key];
    draft.archKey = key;
    draft.family = arch.family;
    draft.lane = arch.defaultLane;
    draft.name = 'Comfy – ' + arch.name.split('/')[0].trim();
    draft.checkpoint = arch.recommended.checkpoint;
    draft.vae = arch.recommended.vae;
    draft.clip = arch.recommended.clip;
    draft.clip_skip = arch.recommended.clip_skip;
    draft.width = arch.recommended.width;
    draft.height = arch.recommended.height;
    draft.steps = arch.recommended.steps;
    draft.cfg = arch.recommended.cfg;
    draft.sampler = arch.recommended.sampler;
    draft.scheduler = arch.recommended.scheduler;
    draft.quality = arch.recommended.quality;
    draft.negative = arch.recommended.negative;
    renderStudio();
  }

  function renderStudio() {
    const arch = COMFY_LITE_ARCHITECTURES[selectedArchKey];
    container.innerHTML = `
    <div class="card comfy-lite-container">
      <div class="actions" style="justify-content:space-between;align-items:flex-start">
        <div>
          <h2>ComfyUI Lite Studio</h2>
          <p class="dim">Visual workflow composer. Select an architecture to automatically load optimal VAE, CLIP, and sampling parameters, stack LoRAs, and designate an active image lane.</p>
        </div>
        <span class="lane-badge ${LANES.find(l => l[0] === draft.lane)?.[2] || 'lane-portrait'}">Active Lane: ${esc(LANES.find(l => l[0] === draft.lane)?.[1] || draft.lane)}</span>
      </div>

      <!-- Architecture Selection Cards -->
      <div>
        <label style="font-weight:600;margin-bottom:8px;display:block">1 · Select Model Architecture</label>
        <div class="comfy-architecture-selector">
          ${Object.entries(COMFY_LITE_ARCHITECTURES).map(([key, a]) => `
            <div class="comfy-arch-card ${selectedArchKey === key ? 'is-selected' : ''}" data-arch="${key}">
              <h4>${esc(a.name)}</h4>
              <p>${esc(a.description)}</p>
              <div class="comfy-rec-badge">Rec: ${a.recommended.width}×${a.recommended.height} · ${a.recommended.steps} steps · CFG ${a.recommended.cfg}</div>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Lane Assignment -->
      <div>
        <label style="font-weight:600;margin-bottom:8px;display:block">2 · Assign Recipe to Image Lane</label>
        <div class="form-grid" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">
          ${LANES.map(([laneKey, laneLabel, laneClass, laneDesc]) => `
            <label class="card" style="padding:10px 14px;cursor:pointer;background:${draft.lane === laneKey ? 'var(--surface-3)' : 'var(--panel)'};border-color:${draft.lane === laneKey ? 'var(--accent-deep)' : 'var(--surface-3)'}">
              <input type="radio" name="comfy-lane" value="${laneKey}" ${draft.lane === laneKey ? 'checked' : ''} style="margin-right:6px">
              <strong>${esc(laneLabel)}</strong>
              <p class="dim small" style="margin:4px 0 0">${esc(laneDesc)}</p>
            </label>
          `).join('')}
        </div>
      </div>

      <!-- Recipe Parameters & Auto-Recommendations -->
      <div>
        <label style="font-weight:600;margin-bottom:8px;display:block">3 · Weights & Sampling Parameters</label>
        <div class="form-grid">
          <label>Workflow recipe name<input id="lite-name" value="${esc(draft.name)}"></label>
          <label>Checkpoint file<input id="lite-checkpoint" value="${esc(draft.checkpoint)}" placeholder="model.safetensors"></label>
          <label>Recommended VAE<input id="lite-vae" value="${esc(draft.vae)}" placeholder="${esc(arch.recommended.vae)}"></label>
          <label>Text encoder / CLIP<input id="lite-clip" value="${esc(draft.clip)}" placeholder="${esc(arch.recommended.clip)}"></label>
        </div>
        <div class="form-grid" style="margin-top:10px">
          <label>Aspect ratio / Resolution
            <div class="actions" style="margin-bottom:6px">
              <button type="button" class="quiet" id="res-portrait">Portrait 832×1216</button>
              <button type="button" class="quiet" id="res-square">Square 1024×1024</button>
              <button type="button" class="quiet" id="res-landscape">Landscape 1216×832</button>
            </div>
            <div style="display:flex;gap:8px;align-items:center">
              <input id="lite-width" type="number" step="64" value="${draft.width}" style="width:90px" title="Width">
              <span>×</span>
              <input id="lite-height" type="number" step="64" value="${draft.height}" style="width:90px" title="Height">
            </div>
          </label>
          <label>Sampling steps<input id="lite-steps" type="number" min="1" max="150" value="${draft.steps}"></label>
          <label>CFG scale<input id="lite-cfg" type="number" min="0.5" max="30" step="0.5" value="${draft.cfg}"></label>
          <label>CLIP last layer<input id="lite-clip-skip" type="number" min="-24" max="-1" step="1" value="${draft.clip_skip}"></label>
        </div>
      </div>

      <!-- Interactive LoRA Stack -->
      <div>
        <div class="actions" style="justify-content:space-between">
          <label style="font-weight:600;margin:0">4 · LoRA Stack (${draft.loras.length} active)</label>
          <button type="button" class="quiet" id="lite-add-lora">+ Add LoRA</button>
        </div>
        <div class="lora-stack" id="lite-lora-list">
          ${draft.loras.length ? draft.loras.map((lora, idx) => `
            <div class="lora-card" data-lora-index="${idx}">
              <div class="lora-card-header">
                <div style="display:flex;align-items:center;gap:10px">
                  <label class="inline-label" style="margin:0"><input type="checkbox" data-lora-enable ${lora.enabled !== false ? 'checked' : ''}><strong>LoRA ${idx + 1}</strong></label>
                  <input data-lora-file value="${esc(lora.filename)}" placeholder="my_lora_name.safetensors" style="width:260px">
                </div>
                <button type="button" class="quiet" data-lora-remove>Remove</button>
              </div>
              <div class="lora-slider-row">
                <span>Model strength:</span>
                <input type="range" data-lora-model-range min="-2.0" max="2.0" step="0.05" value="${lora.strength_model ?? 1.0}">
                <strong data-lora-model-val>${(lora.strength_model ?? 1.0).toFixed(2)}</strong>
              </div>
              <div class="lora-slider-row">
                <span>CLIP strength:</span>
                <input type="range" data-lora-clip-range min="-2.0" max="2.0" step="0.05" value="${lora.strength_clip ?? 1.0}">
                <strong data-lora-clip-val>${(lora.strength_clip ?? 1.0).toFixed(2)}</strong>
              </div>
              <label style="margin-top:4px">Trigger words & tags<input data-lora-triggers value="${esc(lora.triggers || '')}" placeholder="character_tag, outfit_style"></label>
            </div>
          `).join('') : '<p class="dim small" style="padding:12px;background:var(--bg);border-radius:8px">No LoRAs added yet. Add model-specific LoRAs to tune appearance, expressions, or artistic style.</p>'}
        </div>
      </div>

      <!-- Prompt Inspection & Assembly -->
      <details open>
        <summary>5 · Structured Prompt & Triggers</summary>
        <p class="dim small">The quality tags are sent along with the companion's identity prompt and current scene.</p>
        <label>Quality triggers & style tags<textarea id="lite-quality" style="height:60px">${esc(draft.quality)}</textarea></label>
        <label>Negative prompt<textarea id="lite-negative" style="height:60px">${esc(draft.negative)}</textarea></label>
        <div class="actions">
          <button type="button" class="quiet" id="lite-test-prompt">Test prompt assembly</button>
        </div>
        <div id="lite-prompt-preview" style="margin-top:10px"></div>
      </details>

      <!-- Primary Action Buttons -->
      <div class="actions" style="margin-top:14px">
        <button class="act" id="lite-save-lane">Save as ${esc(LANES.find(l => l[0] === draft.lane)?.[1] || draft.lane)} Workflow</button>
        <button class="quiet" id="lite-export-recipe">Download recipe JSON</button>
        <span id="lite-status" class="dim small"></span>
      </div>

      <!-- Advanced Comfy Host & Civitai Downloader -->
      <details style="margin-top:16px;border-top:1px solid var(--surface-3);padding-top:14px">
        <summary>Comfy host connection & Civitai weight downloader</summary>
        <div class="form-grid" style="margin-top:10px">
          <label>Where ComfyUI runs<select id="wc-mode">${options([['local', 'This Hermes host'], ['ssh', 'Another host over SSH']], config.mode)}</select></label>
          <label>SSH host alias<input id="wc-host" value="${esc(config.host)}" placeholder="comfy-host"></label>
          <label>ComfyUI root directory<input id="wc-directory" value="${esc(config.directory)}"></label>
          <label>ComfyUI API endpoint<input id="wc-endpoint" value="${esc(config.endpoint)}"></label>
          <label>Civitai API key<input id="wc-key" type="password" autocomplete="new-password" placeholder="${config.api_key_configured ? 'Saved; blank keeps it' : 'Optional for public models'}"></label>
        </div>
        <button class="quiet" id="wc-save-settings">Save host & key</button>
        <div class="form-grid" style="margin-top:14px">
          <label>Civitai model URL<input id="wc-url" type="url" placeholder="https://civitai.com/models/…"></label>
          <label>Slot<select id="wc-download-slot">${options([['checkpoint', 'Checkpoint'], ['model', 'Diffusion model'], ['lora', 'LoRA'], ['vae', 'VAE'], ['clip', 'Text encoder']], 'checkpoint')}</select></label>
        </div>
        <button class="quiet" id="wc-inspect">Inspect model card</button>
        <div id="wc-inspection"></div>
      </details>
    </div>
    `;

    // Event listeners
    for (const card of container.querySelectorAll('[data-arch]')) {
      card.onclick = () => selectArchitecture(card.dataset.arch);
    }

    for (const radio of container.querySelectorAll('input[name="comfy-lane"]')) {
      radio.onchange = () => {
        draft.lane = radio.value;
        renderStudio();
      };
    }

    $('lite-name').oninput = e => { draft.name = e.target.value; };
    $('lite-checkpoint').oninput = e => { draft.checkpoint = e.target.value; };
    $('lite-vae').oninput = e => { draft.vae = e.target.value; };
    $('lite-clip').oninput = e => { draft.clip = e.target.value; };
    $('lite-width').oninput = e => { draft.width = Number(e.target.value); };
    $('lite-height').oninput = e => { draft.height = Number(e.target.value); };
    $('lite-steps').oninput = e => { draft.steps = Number(e.target.value); };
    $('lite-cfg').oninput = e => { draft.cfg = Number(e.target.value); };
    $('lite-clip-skip').oninput = e => { draft.clip_skip = Number(e.target.value); };
    $('lite-quality').oninput = e => { draft.quality = e.target.value; };
    $('lite-negative').oninput = e => { draft.negative = e.target.value; };

    $('res-portrait').onclick = () => { draft.width = 832; draft.height = 1216; $('lite-width').value = 832; $('lite-height').value = 1216; };
    $('res-square').onclick = () => { draft.width = 1024; draft.height = 1024; $('lite-width').value = 1024; $('lite-height').value = 1024; };
    $('res-landscape').onclick = () => { draft.width = 1216; draft.height = 832; $('lite-width').value = 1216; $('lite-height').value = 832; };

    $('lite-add-lora').onclick = () => {
      draft.loras.push({ filename: '', strength_model: 1.0, strength_clip: 1.0, triggers: '', enabled: true });
      renderStudio();
    };

    for (const card of container.querySelectorAll('.lora-card')) {
      const idx = Number(card.dataset.loraIndex);
      const lora = draft.loras[idx];
      if (!lora) continue;

      card.querySelector('[data-lora-enable]').onchange = e => { lora.enabled = e.target.checked; };
      card.querySelector('[data-lora-file]').oninput = e => { lora.filename = e.target.value; };
      card.querySelector('[data-lora-triggers]').oninput = e => { lora.triggers = e.target.value; };

      const modelRange = card.querySelector('[data-lora-model-range]');
      const modelVal = card.querySelector('[data-lora-model-val]');
      modelRange.oninput = () => {
        lora.strength_model = Number(modelRange.value);
        modelVal.textContent = lora.strength_model.toFixed(2);
      };

      const clipRange = card.querySelector('[data-lora-clip-range]');
      const clipVal = card.querySelector('[data-lora-clip-val]');
      clipRange.oninput = () => {
        lora.strength_clip = Number(clipRange.value);
        clipVal.textContent = lora.strength_clip.toFixed(2);
      };

      card.querySelector('[data-lora-remove]').onclick = () => {
        draft.loras.splice(idx, 1);
        renderStudio();
      };
    }

    $('lite-test-prompt').onclick = async () => {
      const loraTriggers = draft.loras.filter(l => l.enabled !== false && l.triggers).map(l => l.triggers).join(', ');
      const combinedQuality = [draft.quality, loraTriggers].filter(Boolean).join(', ');
      const previewEl = $('lite-prompt-preview');
      previewEl.innerHTML = `
        <div class="card" style="background:var(--bg);border-color:var(--edge)">
          <h4>Assembled Prompt Breakdown</h4>
          <p style="font-size:13px;line-height:1.6">
            <span style="color:var(--accent);font-weight:600">[Quality & Style]</span> ${esc(combinedQuality)}<br>
            <span style="color:var(--warn);font-weight:600">[Companion Identity]</span> (Included from SOUL appearance${draft.lane === 'scenery' ? ' — <em>disabled for scenery lane</em>' : ''})<br>
            <span style="color:var(--good);font-weight:600">[Scene & Wardrobe]</span> (Composed dynamically during generation)<br>
            <span style="color:var(--ink-2);font-weight:600">[Negative]</span> ${esc(draft.negative)}
          </p>
          <p class="dim small">Resolution: ${draft.width}×${draft.height} · Sampling: ${draft.steps} steps @ CFG ${draft.cfg} · Architecture: ${esc(arch.name)}</p>
        </div>
      `;
    };

    $('lite-save-lane').onclick = async () => {
      const { graph, mappings } = buildModularWorkflowGraph(draft);
      const loraTriggers = draft.loras.filter(l => l.enabled !== false && l.triggers).map(l => l.triggers).join(', ');
      const combinedQuality = [draft.quality, loraTriggers].filter(Boolean).join(', ');

      const preset = {
        id: 'comfy-' + presetSuffix(),
        name: draft.name || 'Comfy workflow',
        category: draft.lane === 'default' ? 'portrait' : draft.lane,
        provider: 'comfyui',
        endpoint: config.endpoint || 'http://127.0.0.1:8188',
        family: draft.family,
        include_identity: draft.lane !== 'scenery',
        parts: { quality: combinedQuality },
        negative: draft.negative || '',
        width: Number(draft.width || 832),
        height: Number(draft.height || 1216),
        steps: Number(draft.steps || 22),
        cfg: Number(draft.cfg || 5.5),
        seed: -1,
        workflow: graph,
        mappings: mappings
      };

      onCreate(preset, draft.lane);
      $('lite-status').textContent = `✓ Recipe created and designated as ${draft.lane} lane! Save image settings to keep changes.`;
      $('lite-status').className = 'status-good small';
      notice(`Workflow added and set as ${draft.lane} lane.`);
    };

    $('lite-export-recipe').onclick = () => {
      const { graph, mappings } = buildModularWorkflowGraph(draft);
      const recipe = {
        name: draft.name,
        family: draft.family,
        lane: draft.lane,
        width: draft.width,
        height: draft.height,
        steps: draft.steps,
        cfg: draft.cfg,
        workflow: graph,
        mappings: mappings
      };
      downloadJSON((draft.name.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'comfy-recipe') + '.json', recipe);
    };

    // Host & Civitai Downloader handlers
    $('wc-save-settings').onclick = async () => {
      config = await post('/workflows/settings', {
        mode: $('wc-mode').value,
        host: $('wc-host').value,
        directory: $('wc-directory').value,
        endpoint: $('wc-endpoint').value,
        api_key: $('wc-key').value
      });
      $('wc-key').value = '';
      $('wc-key').placeholder = config.api_key_configured ? 'Saved; blank keeps it' : 'Optional for public models';
      notice('Comfy host settings saved.');
    };

    function showInspection() {
      const d = inspected;
      $('wc-inspection').innerHTML = `
        <div class="card" style="margin-top:10px">
          <h4>${esc(d.name)}</h4>
          <p>${esc(d.base_model)} · ${esc(d.type)}</p>
          <label>Version<select id="wc-version">${options(d.versions.map(v => [String(v.id), v.name + ' · ' + v.base_model]), String(d.version_id))}</select></label>
          <label>Weight file<select id="wc-file">${options(d.files.map(f => [String(f.id), f.name + ' · ' + (f.size_bytes / 1024 ** 3).toFixed(2) + ' GB']), '')}</select></label>
          <p>Triggers: ${esc(d.trigger_words.join(', ') || 'None listed')}</p>
          ${licenceNotice(d.license, d.page)}
          <button class="quiet" id="wc-download" ${d.files.length ? '' : 'disabled'}>Download selected weights</button>
        </div>
      `;
      $('wc-version').onchange = async e => {
        inspected = await post('/workflows/inspect', { url: $('wc-url').value, version_id: Number(e.target.value) });
        showInspection();
      };
      $('wc-download').onclick = () => {
        const target = $('wc-download-slot').value;
        action('/workflows/download', { url: $('wc-url').value, version_id: d.version_id, file_id: Number($('wc-file').value), slot: target }, async r => {
          if (target === 'lora') {
            draft.loras.push({ filename: r.filename, strength_model: 1.0, strength_clip: 1.0, triggers: (r.trigger_words || []).join(', '), enabled: true });
          } else if (target === 'checkpoint') {
            draft.checkpoint = r.filename;
          }
          renderStudio();
          notice('Weights downloaded and added to recipe slot.');
        });
      };
    }

    $('wc-inspect').onclick = async () => {
      inspected = await post('/workflows/inspect', { url: $('wc-url').value });
      showInspection();
    };
  }

  renderStudio();
}
