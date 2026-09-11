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

test('fidelity placeholders match backend presets', () => {
  const {app, document} = harness();
  app.updateOverridePlaceholders('fine');
  assert.match(document.getElementById('cfg-override-basecell').placeholder, /0.08/);
  assert.match(document.getElementById('cfg-override-solver-endtime').placeholder, /3000/);
  app.updateOverridePlaceholders('fast');
  assert.match(document.getElementById('cfg-override-nearwake').placeholder, /2/);
});

test('mesher policy and first-layer mode reach the config overrides', () => {
  const {app, document} = harness();
  document.getElementById('cfg-override-layer-firstlayer').value = '0.14';
  document.getElementById('cfg-override-firstlayer-mode').value = 'absolute';
  document.getElementById('cfg-override-firstlayer-height').value = '0.0005';
  document.getElementById('cfg-override-cfmesh-groundrefine').value = 'on';
  document.getElementById('cfg-override-cfmesh-layermode').value = 'global';
  document.getElementById('cfg-override-cfmesh-optimise').value = 'off';
  app.buildConfigFromVisualForm();
  const overrides = app.activeConfig.overrides;
  assert.equal(overrides.layers.first_layer_thickness, 0.14);
  assert.equal(overrides.layers.first_layer_mode, 'absolute');
  assert.equal(overrides.layers.first_layer_height, 0.0005);
  assert.equal(overrides.cfmesh.ground_refine, true);
  assert.equal(overrides.cfmesh.layer_mode, 'global');
  assert.equal(overrides.cfmesh.optimise_layer, false);
  // Untouched override keys survive the round trip.
  assert.equal(overrides.mesh_params.boundary_cell_size, 0.03);
});

test('blank mesher policy fields leave the profile in charge', () => {
  const {app} = harness();
  app.buildConfigFromVisualForm();
  const overrides = app.activeConfig.overrides || {};
  assert.equal((overrides.cfmesh || {}).ground_refine, undefined);
  assert.equal((overrides.cfmesh || {}).layer_mode, undefined);
  assert.equal((overrides.layers || {}).first_layer_mode, undefined);
  assert.equal((overrides.layers || {}).first_layer_height, undefined);
  // "Auto" hints stay on the static HTML labels until the schema fetch answers.
  const {document} = harness();
  assert.equal(app.mesherDefaults, undefined);
  app.refreshMesherPolicyHints();
  assert.match(document.getElementById('cfg-override-firstlayer-mode').value ?? '', /^$/);
});
