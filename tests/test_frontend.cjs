// Run with node --test tests/test_frontend.cjs; no browser packages required.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const elements = new Map();
  function element() {
    return { value: '', innerHTML: '', style: {}, children: [], dataset: {},
      appendChild(child) { this.children.push(child); },
      querySelector() { return element(); }, addEventListener() {},
      classList: { add() {}, remove() {} } };
  }
  const document = {activeElement: null,
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    createElement: element,
  };
  const context = vm.createContext({document, window: {addEventListener() {}}, console, setTimeout() {}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/rapidfoam/web/static/js/app.js'), 'utf8') + '\nthis.CFDApp = CFDApp;', context);
  const app = Object.create(context.CFDApp.prototype);
  app.activeConfig = {case_name: 'demo', stl_files: ['geometry.stl'],
    parallel: {method: 'hierarchical', n_procs: 16, custom: 'keep'},
    slurm: {nodes: 3, cpus_per_task: 2}, flow: {custom: 'keep'}, outputs: {custom: 'keep'},
    overrides: {solver: {end_time: 999, custom: 123}, mesh_params: {boundary_cell_size: 0.03}, advanced: {keep: true}}};
  app.syncConfigToJsonDrawer = () => {};
  app.updateDomainBoxVisualization = async () => {};
  app.showToast = () => {};
  document.getElementById('cfg-parallel-method').value = 'hierarchical';
  return {app, context, document, elements};
}

// Trimmed copy of GET /api/config/schema-defaults: the tables the Overrides
// "Auto" hints are rendered from. tests/test_web_api.py asserts the server
// payload carries these keys, so this fixture cannot drift unnoticed.
const SCHEMA = {
  default_config: {
    solver: {purge_write: 2},
    force_refs: {Aref: 1.0, lRef: 1.0},
    layers: {min_thickness: 0.05},
    fluid: {rho: 1.225, nu: 0.00001516},
    turbulence: {model: 'kOmegaSST', intensity: 0.005, nut_ratio: 10},
  },
  fidelity_presets: {
    fast: {cells_per_length: 20, surface_level: [3, 4], edge_level: 5,
      wake_levels_below_surface: [1, 2], n_layers: 3, expansion_ratio: 1.3,
      first_layer_thickness: 0.4, end_time: 800, write_interval: 400},
    standard: {cells_per_length: 30, surface_level: [4, 5], edge_level: 6,
      wake_levels_below_surface: [1, 3], n_layers: 5, expansion_ratio: 1.2,
      first_layer_thickness: 0.3, end_time: 1500, write_interval: 500},
    fine: {cells_per_length: 37.5, surface_level: [5, 6], edge_level: 7,
      wake_levels_below_surface: [1, 3], n_layers: 6, expansion_ratio: 1.15,
      first_layer_thickness: 0.2, end_time: 3000, write_interval: 500},
  },
  mesher_defaults: {
    cfmesh: {layers: {first_layer_mode: 'relative'},
      cfmesh: {ground_refine: false, parallel_meshing: 'auto', optimise_layer: 'auto'}},
    snappy: {layers: {first_layer_mode: 'relative'}},
  },
  mesher_keys: {
    cfmesh: {mesh_params: ['base_cell_size', 'cells_per_length', 'surface_level', 'edge_level',
      'min_cell_size', 'wake_levels_below_surface'].map((key) => ({key}))},
    snappy: {mesh_params: ['base_cell_size', 'cells_per_length', 'surface_level', 'edge_level',
      'wake_levels_below_surface'].map((key) => ({key}))},
  },
  available_meshers: ['cfmesh', 'snappy'],
};

async function loadSchema(app, context, schema = SCHEMA) {
  context.fetch = async () => ({ok: true, json: async () => schema});
  await app.loadSchemaDefaults();
}

test('visual edits retain hidden configuration and clear only exposed blank overrides', () => {
  const {app} = harness();
  app.buildConfigFromVisualForm();
  assert.equal(app.activeConfig.parallel.method, 'hierarchical');
  assert.equal(app.activeConfig.parallel.custom, 'keep');
  assert.equal(app.activeConfig.slurm.nodes, 3);
  assert.equal(app.activeConfig.slurm.cpus_per_task, 2);
  assert.equal(app.activeConfig.flow.custom, 'keep');
  assert.equal(app.activeConfig.outputs.custom, 'keep');
  assert.equal(app.activeConfig.overrides.solver.custom, 123);
  assert.equal(app.activeConfig.overrides.solver.end_time, undefined);
  assert.equal(app.activeConfig.overrides.mesh_params.boundary_cell_size, 0.03);
  assert.equal(app.activeConfig.overrides.advanced.keep, true);
  app.clearAllOverrides();
  assert.equal(app.activeConfig.overrides, undefined);
});

test('Validate calls the read-only API and Save does not generate', async () => {
  const {app, context} = harness();
  const requests = [];
  context.fetch = async (url, options) => { requests.push([url, JSON.parse(options.body)]); return {ok: true, json: async () => ({case_name: 'demo'})}; };
  await app.validateCurrentConfig();
  assert.equal(requests[0][0], '/api/case/validate');
  await app.saveCurrentConfig(false);
  assert.equal(requests[1][1].generate_locally, false);
  assert.equal(requests[1][1].save_config, true);
});

test('bundled geometry loads in the viewer', async () => {
  const {app, context} = harness();
  const loaded = [];
  app.viewer = {clearSTLs() {}, addSTLFromArrayBuffer(buffer, name) {loaded.push(name);}, getCombinedBoundingBox() {return {};} };
  context.fetch = async () => ({ok: true, arrayBuffer: async () => new ArrayBuffer(0)});
  await app.loadAllActiveSTLsFromServer();
  assert.deepEqual(loaded, ['geometry.stl']);
});

test('queue, archive, STL names and toasts escape untrusted markup', () => {
  const {app, document} = harness();
  const attack = '<img src=x onerror="boom()">';
  app.renderQueueTable([{job_id: attack, name: attack, state: attack}]);
  const queue = document.getElementById('slurm-queue-tbody').children[0].innerHTML;
  assert.ok(!queue.includes('<img'));
  assert.ok(queue.includes('&lt;img'));
  app.showToast = Object.getPrototypeOf(app).showToast;
  app.showToast(attack);
  const toast = document.getElementById('toast-container').children[0].innerHTML;
  assert.ok(!toast.includes('<img'));
  assert.ok(toast.includes('&lt;img'));
  app.viewer = {getSTLColor() {return '#123456';}};
  app.renderActiveSTLChips([attack]);
  const chip = document.getElementById('stl-chip-list').children[0];
  assert.ok(!chip.innerHTML.includes('<img'));
  app.archiveCases = [{name: attack, status: attack, fidelity: attack, direction: attack, modified: attack, stl_name: attack, downforce: attack, drag: attack}];
  app.currentArchiveFilter = 'all';
  app.archiveSearchTerm = '';
  app.renderCasesArchiveTable();
  const archive = document.getElementById('archive-tbody').children[0];
  assert.ok(!archive.innerHTML.includes('<img'));
});

test('fidelity placeholders match backend presets', async () => {
  const {app, context, document} = harness();
  await loadSchema(app, context);
  app.updateOverridePlaceholders('fine');
  assert.match(document.getElementById('cfg-override-basecell').placeholder, /0.08/);
  assert.match(document.getElementById('cfg-override-solver-endtime').placeholder, /3000/);
  app.updateOverridePlaceholders('fast');
  assert.match(document.getElementById('cfg-override-nearwake').placeholder, /2/);
});

test('overrides Auto hints follow the selected mesher and fidelity', async () => {
  const {app, context, document} = harness();
  await loadSchema(app, context);
  const engine = document.getElementById('cfg-mesher-engine');

  engine.value = 'cfmesh';
  app.updateOverridePlaceholders('standard');
  assert.equal(document.getElementById('cfg-override-edge').placeholder, 'Auto (cfmesh: 6)');
  assert.equal(document.getElementById('cfg-override-nearwake').placeholder,
    'Auto (cfmesh: level 3 = surface L4 - 1)');
  assert.equal(document.getElementById('cfg-override-mincellsize').placeholder, 'Auto (cfmesh: body)');
  assert.equal(document.getElementById('cfg-override-mincellsize').disabled, false);
  // A shared key the engine reads differently says so in the same hint.
  assert.equal(document.getElementById('cfg-override-surf-max').placeholder,
    'Max (cfmesh: 5 — cfMesh refines feature edges one level finer on its own)');

  // Switching the engine re-labels the section and drops the cfMesh-only floor.
  engine.value = 'snappy';
  app.refreshMesherPolicyHints();
  assert.equal(document.getElementById('cfg-override-edge').placeholder, 'Auto (snappy: 6)');
  assert.equal(document.getElementById('cfg-override-mincellsize').disabled, true);
  assert.equal(document.getElementById('cfg-override-mincellsize').placeholder,
    "Not read by snappy — cfMesh's global automatic-refinement floor");
  // Mesher-independent controls keep the preset wording…
  assert.equal(document.getElementById('cfg-override-solver-endtime').placeholder, 'Auto / Preset (1500)');
  // …while the profile-owned first-layer mode is tagged with the engine.
  const mode = document.getElementById('cfg-override-firstlayer-mode');
  mode.options = [{textContent: ''}];
  app.updateOverridePlaceholders();
  assert.equal(mode.options[0].textContent, 'Auto (snappy: relative)');

  // Fidelity switch: levels and wake offsets come from the preset.
  app.updateOverridePlaceholders('fine');
  assert.equal(document.getElementById('cfg-override-surf-min').placeholder, 'Min (snappy: 5)');
  assert.equal(document.getElementById('cfg-override-nearwake').placeholder,
    'Auto (snappy: level 4 = surface L5 - 1)');
  assert.equal(document.getElementById('cfg-override-basecell').placeholder,
    'Auto (snappy: model length / 37.5 = 0.08 m on a 3.0 m car)');
});

test('without the schema the static Auto labels stay in place', () => {
  const {app, document} = harness();
  // No /api/config/schema-defaults answer: nothing may overwrite the HTML text.
  app.updateOverridePlaceholders('fine');
  assert.equal(document.getElementById('cfg-override-edge').placeholder, undefined);
  assert.equal(document.getElementById('cfg-override-mincellsize').disabled, undefined);
});

test('mesher policy and first-layer mode reach the config overrides', () => {
  const {app, document} = harness();
  document.getElementById('cfg-override-layer-firstlayer').value = '0.14';
  document.getElementById('cfg-override-firstlayer-mode').value = 'absolute';
  document.getElementById('cfg-override-firstlayer-height').value = '0.0005';
  document.getElementById('cfg-override-cfmesh-groundrefine').value = 'on';
  document.getElementById('cfg-override-cfmesh-parallel').value = 'off';
  document.getElementById('cfg-override-cellsperlength').value = '45';
  document.getElementById('cfg-override-mincellsize').value = '0.002';
  document.getElementById('cfg-override-cfmesh-optimise').value = 'off';
  app.buildConfigFromVisualForm();
  const overrides = app.activeConfig.overrides;
  assert.equal(overrides.layers.first_layer_thickness, 0.14);
  assert.equal(overrides.layers.first_layer_mode, 'absolute');
  assert.equal(overrides.layers.first_layer_height, 0.0005);
  assert.equal(overrides.cfmesh.ground_refine, true);
  assert.equal(overrides.cfmesh.parallel_meshing, false);
  // Sizing knobs the form owns, including the min-cell alias/float handling.
  assert.equal(overrides.mesh_params.cells_per_length, 45);
  assert.equal(overrides.mesh_params.min_cell_size, 0.002);
  assert.equal(overrides.cfmesh.optimise_layer, false);
  // Untouched override keys survive the round trip.
  assert.equal(overrides.mesh_params.boundary_cell_size, 0.03);
});

test('blank mesher policy fields leave the profile in charge', () => {
  const {app} = harness();
  app.buildConfigFromVisualForm();
  const overrides = app.activeConfig.overrides || {};
  assert.equal((overrides.cfmesh || {}).ground_refine, undefined);
  assert.equal((overrides.cfmesh || {}).parallel_meshing, undefined);
  assert.equal((overrides.layers || {}).first_layer_mode, undefined);
  assert.equal((overrides.layers || {}).first_layer_height, undefined);
  // "Auto" hints stay on the static HTML labels until the schema fetch answers.
  const {document} = harness();
  assert.equal(app.mesherDefaults, undefined);
  app.refreshMesherPolicyHints();
  assert.match(document.getElementById('cfg-override-firstlayer-mode').value ?? '', /^$/);
});
