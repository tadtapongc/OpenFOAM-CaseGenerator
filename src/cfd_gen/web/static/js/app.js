/**
 * OpenFOAM Case Generator Studio - Main Application Controller
 */

class CFDApp {
  constructor() {
    this.viewer = null;
    this.charts = null;
    this.clusterConnected = false;
    this.pollInterval = null;
    this.isSyncingFromJson = false;
    this.currentSTLName = null;

    this.activeConfig = {
      case_name: "my_case",
      stl_files: ["geometry.stl"],
      stl_dir: "stl",
      case_dir: "cases",
      fidelity: "standard",
      flow: {
        velocity: 16.67,
        direction: "-z",
        ground: true,
      },
      outputs: {
        drag_axis: "-z",
        downforce_axis: "-y",
      },
      domain_box: "auto",
      symmetry_plane: 0.0,
      ground_clearance: 0.035,
      domain_faces: {
        "-x": "symmetry",
        "+x": "farField",
        "-y": "ground",
        "+y": "farField",
        "+z": "inlet",
        "-z": "outlet",
      },
      parallel: {
        n_procs: 32,
        method: "scotch",
      },
      slurm: {
        qos: "cu_hpc",
        partition: "cpu",
        nodes: 1,
        time: "08:00:00",
        mem_per_cpu: "2G",
        openfoam_module: [
          "GCC/11.3.0",
          "OpenMPI/4.1.4-GCC-11.3.0"
        ],
        openfoam_source: "$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc",
        use_tmpdir: true,
        sync_interval: 15,
      },
      _comment_overrides: "Expert overrides — all fields below have built-in defaults in fidelity presets. Uncomment only if manual tuning is needed.",
      _optional_overrides_example: {
        mesh_params: {
          _base_cell_size: 0.10,
          _surface_level: [4, 5],
          _edge_level: 6,
          _near_wake_level: 3,
          _far_wake_level: 1,
        }
      }
    };

    this.init();
  }

  async init() {
    // 1. Initialize components
    this.viewer = new STLViewer('stl-viewer-container');
    this.charts = new TelemetryCharts();

    // 2. Bind UI event listeners
    this.bindNavigation();
    this.bindSubtabs();
    this.bindConfigFormInputs();
    this.bindJsonDrawer();
    this.bindSTLUpload();
    this.bindSSHModal();
    this.bindTelemetryEvents();

    // 3. Load initial data from backend
    await this.loadLocalClusterConfig();
    await this.checkClusterStatus();
    await this.loadTemplatesList();
    // Automatically load configs/config.json as the default config
    await this.loadConfigFile('config.json', true);
    await this.loadExistingSTLs();
    await this.loadCasesArchive();

    // 5. Start background queue polling
    this.pollInterval = setInterval(() => {
      if (this.clusterConnected) {
        this.refreshQueue();
      }
      const activeTab = document.querySelector('.nav-tab.active');
      if (activeTab && activeTab.dataset.tab === 'telemetry-tab') {
        this.pollTelemetry();
      }
    }, 5000);
  }

  // -------------------------------------------------------------
  // Navigation & Sub-Tabs
  // -------------------------------------------------------------
  bindNavigation() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        tabs.forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');

        const targetId = tab.dataset.tab;
        document.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));
        const pane = document.getElementById(targetId);
        if (pane) pane.classList.add('active');

        if (targetId === 'config-tab' && this.viewer) {
          setTimeout(() => this.viewer.onResize(), 50);
        } else if (targetId === 'telemetry-tab') {
          this.pollTelemetry();
        } else if (targetId === 'cases-tab') {
          this.loadCasesArchive();
        }
      });
    });
  }

  bindSubtabs() {
    const subtabs = document.querySelectorAll('.sub-tab');
    subtabs.forEach((st) => {
      st.addEventListener('click', () => {
        subtabs.forEach((s) => s.classList.remove('active'));
        st.classList.add('active');

        const targetId = st.dataset.subtab;
        document.querySelectorAll('.subtab-content').forEach((sc) => sc.classList.remove('active'));
        const content = document.getElementById(targetId);
        if (content) content.classList.add('active');
      });
    });
  }

  // -------------------------------------------------------------
  // Bidirectional Config Synchronization
  // -------------------------------------------------------------
  bindConfigFormInputs() {
    // Fidelity cards
    const fidelityCards = document.querySelectorAll('.fidelity-card');
    fidelityCards.forEach((card) => {
      card.addEventListener('click', () => {
        fidelityCards.forEach((c) => c.classList.remove('selected'));
        card.classList.add('selected');
        const radio = card.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;
        this.buildConfigFromVisualForm();
      });
    });

    // Velocity slider <-> km/h <-> m/s dual-sync
    const sliderVel = document.getElementById('slider-velocity');
    const inputKmh = document.getElementById('cfg-flow-velocity-kmh');
    const inputMs = document.getElementById('cfg-flow-velocity-ms');

    if (sliderVel && inputKmh && inputMs) {
      sliderVel.addEventListener('input', (e) => {
        const kmh = parseFloat(e.target.value);
        inputKmh.value = kmh.toFixed(1);
        inputMs.value = (kmh / 3.6).toFixed(2);
        this.buildConfigFromVisualForm();
      });

      inputKmh.addEventListener('input', (e) => {
        const kmh = parseFloat(e.target.value) || 0;
        sliderVel.value = Math.min(Math.max(kmh, 5), 150);
        inputMs.value = (kmh / 3.6).toFixed(2);
        this.buildConfigFromVisualForm();
      });

      inputMs.addEventListener('input', (e) => {
        const ms = parseFloat(e.target.value) || 0;
        const kmh = ms * 3.6;
        inputKmh.value = kmh.toFixed(1);
        sliderVel.value = Math.min(Math.max(kmh, 5), 150);
        this.buildConfigFromVisualForm();
      });
    }

    // Domain box selector (auto vs custom)
    const domainBoxSel = document.getElementById('cfg-domain-box');
    const customDomainDiv = document.getElementById('custom-domain-container');
    if (domainBoxSel && customDomainDiv) {
      domainBoxSel.addEventListener('change', () => {
        customDomainDiv.style.display = domainBoxSel.value === 'custom' ? 'block' : 'none';
        this.buildConfigFromVisualForm();
      });
    }

    // Overrides toggle
    const chkOverrides = document.getElementById('chk-enable-overrides');
    const overridesContainer = document.getElementById('overrides-controls-container');
    const noticeBox = document.getElementById('overrides-disabled-notice');
    if (chkOverrides) {
      chkOverrides.addEventListener('change', (e) => {
        const enabled = e.target.checked;
        if (overridesContainer) overridesContainer.style.display = enabled ? 'grid' : 'none';
        if (noticeBox) noticeBox.style.display = enabled ? 'none' : 'block';
        this.buildConfigFromVisualForm();
      });
    }

    // Ground level style selector (2 + 1 styles)
    const groundStyleSelect = document.getElementById('cfg-ground-style');
    groundStyleSelect?.addEventListener('change', (e) => {
      const val = e.target.value;
      const groupRel = document.getElementById('group-ground-relative');
      const groupAbs = document.getElementById('group-ground-absolute');
      if (groupRel) groupRel.style.display = val === 'relative' ? 'block' : 'none';
      if (groupAbs) groupAbs.style.display = val === 'absolute' ? 'block' : 'none';
      this.buildConfigFromVisualForm();
      this.updateDomainBoxVisualization();
    });

    // Generic input change listeners on all visual inputs
    const form = document.getElementById('case-config-form');
    if (form) {
      form.addEventListener('input', () => this.buildConfigFromVisualForm());
      form.addEventListener('change', () => this.buildConfigFromVisualForm());
    }

    // Action buttons
    document.getElementById('btn-validate-config')?.addEventListener('click', () => this.validateCurrentConfig());
    document.getElementById('btn-save-config')?.addEventListener('click', () => this.saveCurrentConfig(false));
    document.getElementById('btn-submit-case')?.addEventListener('click', () => this.saveCurrentConfig(true));
    document.getElementById('btn-quick-run')?.addEventListener('click', () => this.saveCurrentConfig(true));

    document.getElementById('btn-reset-defaults')?.addEventListener('click', async () => {
      if (confirm('Reset all fields to configs/config.json?')) {
        await this.loadConfigFile('config.json');
        this.showToast('Reset to configs/config.json', 'info');
      }
    });

    // Template loader (auto-loads on change)
    const selectTemplate = document.getElementById('select-template');
    selectTemplate?.addEventListener('change', async (e) => {
      if (e.target.value) {
        await this.loadConfigFile(e.target.value);
      }
    });
    document.getElementById('btn-load-template')?.addEventListener('click', async () => {
      if (selectTemplate && selectTemplate.value) {
        await this.loadConfigFile(selectTemplate.value);
      }
    });

    // Auto symmetry plane shortcut in Domain & Ground form
    document.getElementById('btn-auto-sym-inline')?.addEventListener('click', () => this.autoSymmetryPlaneCenter());
  }

  updateVisualFormFromConfig(cfg) {
    if (!cfg) return;

    // General
    this.setVal('cfg-case-name', cfg.case_name || 'my_case');

    const fidelity = cfg.fidelity || 'standard';
    document.querySelectorAll('.fidelity-card').forEach((card) => {
      const match = card.dataset.fidelity === fidelity;
      card.classList.toggle('selected', match);
      const r = card.querySelector('input');
      if (r) r.checked = match;
    });

    // Flow
    const flow = cfg.flow || {};
    const velMs = flow.velocity !== undefined ? flow.velocity : 16.67;
    this.setVal('cfg-flow-velocity-ms', velMs);
    const kmh = velMs * 3.6;
    this.setVal('cfg-flow-velocity-kmh', kmh.toFixed(1));
    this.setVal('slider-velocity', Math.min(Math.max(kmh, 5), 150));
    this.setVal('cfg-flow-direction', flow.direction || '-z');
    this.setCheck('cfg-flow-ground', flow.ground !== false);

    // Outputs
    const outputs = cfg.outputs || {};
    this.setVal('cfg-outputs-drag', outputs.drag_axis || '-z');
    this.setVal('cfg-outputs-downforce', outputs.downforce_axis || '-y');

    // Domain & Boundaries
    if (typeof cfg.domain_box === 'object' && cfg.domain_box !== null) {
      this.setVal('cfg-domain-box', 'custom');
      document.getElementById('custom-domain-container').style.display = 'block';
      this.setVal('cfg-domain-min', JSON.stringify(cfg.domain_box.min || []));
      this.setVal('cfg-domain-max', JSON.stringify(cfg.domain_box.max || []));
    } else {
      this.setVal('cfg-domain-box', 'auto');
      document.getElementById('custom-domain-container').style.display = 'none';
    }

    const sym = cfg.symmetry_plane !== undefined ? cfg.symmetry_plane : (cfg._symmetry_plane !== undefined ? cfg._symmetry_plane : 0.0);
    this.setVal('cfg-symmetry-plane', sym);

    // Ground Level Specification (2 + 1 Styles)
    const groupRel = document.getElementById('group-ground-relative');
    const groupAbs = document.getElementById('group-ground-absolute');

    if (cfg.ground_clearance !== undefined && cfg.ground_clearance !== null) {
      // Style 1: Relative Ride Height
      this.setVal('cfg-ground-style', 'relative');
      this.setVal('cfg-ground-clearance', cfg.ground_clearance);
      if (groupRel) groupRel.style.display = 'block';
      if (groupAbs) groupAbs.style.display = 'none';
    } else if (cfg.ground_plane !== undefined && cfg.ground_plane !== null) {
      // Style 2: Absolute CAD Ground Plane
      this.setVal('cfg-ground-style', 'absolute');
      this.setVal('cfg-ground-plane', cfg.ground_plane);
      if (groupRel) groupRel.style.display = 'none';
      if (groupAbs) groupAbs.style.display = 'block';
    } else {
      // Style 0 / None (Default in config.json): Touching CAD Bottom
      this.setVal('cfg-ground-style', 'none');
      this.setVal('cfg-ground-clearance', cfg._ground_clearance !== undefined ? cfg._ground_clearance : 0.035);
      this.setVal('cfg-ground-plane', cfg._ground_plane !== undefined ? cfg._ground_plane : 0.0);
      if (groupRel) groupRel.style.display = 'none';
      if (groupAbs) groupAbs.style.display = 'none';
    }

    const faces = cfg.domain_faces || {};
    this.setVal('cfg-face-neg-x', faces['-x'] || 'symmetry');
    this.setVal('cfg-face-pos-x', faces['+x'] || 'farField');
    this.setVal('cfg-face-neg-y', faces['-y'] || 'ground');
    this.setVal('cfg-face-pos-y', faces['+y'] || 'farField');
    this.setVal('cfg-face-pos-z', faces['+z'] || 'inlet');
    this.setVal('cfg-face-neg-z', faces['-z'] || 'outlet');

    // Parallel & SLURM
    const par = cfg.parallel || {};
    this.setVal('cfg-parallel-procs', par.n_procs || 32);
    this.setVal('cfg-parallel-method', par.method || 'scotch');

    const slurm = cfg.slurm || {};
    this.setVal('cfg-slurm-qos', slurm.qos || 'cu_hpc');
    this.setVal('cfg-slurm-partition', slurm.partition || 'cpu');
    this.setVal('cfg-slurm-time', slurm.time || '08:00:00');
    this.setVal('cfg-slurm-mem', slurm.mem_per_cpu || '2G');
    this.setVal('cfg-slurm-source', slurm.openfoam_source || '$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc');
    
    if (Array.isArray(slurm.openfoam_module)) {
      this.setVal('cfg-slurm-modules', slurm.openfoam_module.join(', '));
    } else if (slurm.openfoam_module) {
      this.setVal('cfg-slurm-modules', slurm.openfoam_module);
    } else {
      this.setVal('cfg-slurm-modules', 'GCC/11.3.0, OpenMPI/4.1.4-GCC-11.3.0');
    }

    this.setCheck('cfg-slurm-tmpdir', slurm.use_tmpdir !== false);
    this.setVal('cfg-slurm-sync', slurm.sync_interval || 15);

    // Overrides (mesh_params)
    const overrides = cfg.overrides || {};
    const meshParams = overrides.mesh_params || cfg.mesh_params || null;
    const hasActiveOverrides = meshParams && Object.keys(meshParams).some((k) => !k.startsWith('_'));

    const chkOverrides = document.getElementById('chk-enable-overrides');
    const overridesContainer = document.getElementById('overrides-controls-container');
    const noticeBox = document.getElementById('overrides-disabled-notice');

    if (chkOverrides) chkOverrides.checked = !!hasActiveOverrides;
    if (overridesContainer) overridesContainer.style.display = hasActiveOverrides ? 'grid' : 'none';
    if (noticeBox) noticeBox.style.display = hasActiveOverrides ? 'none' : 'block';

    if (hasActiveOverrides && meshParams) {
      if (meshParams.base_cell_size !== undefined) this.setVal('cfg-override-basecell', meshParams.base_cell_size);
      if (Array.isArray(meshParams.surface_level) && meshParams.surface_level.length >= 2) {
        this.setVal('cfg-override-surf-min', meshParams.surface_level[0]);
        this.setVal('cfg-override-surf-max', meshParams.surface_level[1]);
      }
      if (meshParams.edge_level !== undefined) this.setVal('cfg-override-edge', meshParams.edge_level);
      if (meshParams.near_wake_level !== undefined) this.setVal('cfg-override-nearwake', meshParams.near_wake_level);
      if (meshParams.far_wake_level !== undefined) this.setVal('cfg-override-farwake', meshParams.far_wake_level);
    }

    // Render active STL chips
    const newStls = cfg.stl_files || [];
    this.renderActiveSTLChips(newStls);
    if (newStls.length > 0 && newStls[0] !== this.currentSTLName) {
      this.currentSTLName = newStls[0];
      this.loadSTLGeometryFromServer(newStls[0]);
    }
  }

  buildConfigFromVisualForm() {
    if (this.isSyncingFromJson) return;
    const cfg = { ...this.activeConfig };

    // General
    cfg.case_name = this.getVal('cfg-case-name') || 'my_case';

    const selectedFidelityCard = document.querySelector('.fidelity-card.selected');
    cfg.fidelity = selectedFidelityCard ? selectedFidelityCard.dataset.fidelity : 'standard';

    // Flow
    cfg.flow = {
      velocity: parseFloat(this.getVal('cfg-flow-velocity-ms')) || 16.67,
      direction: this.getVal('cfg-flow-direction') || '-z',
      ground: this.getCheck('cfg-flow-ground'),
    };

    // Outputs
    cfg.outputs = {
      drag_axis: this.getVal('cfg-outputs-drag') || '-z',
      downforce_axis: this.getVal('cfg-outputs-downforce') || '-y',
    };

    // Domain
    const domainChoice = this.getVal('cfg-domain-box');
    if (domainChoice === 'custom') {
      try {
        cfg.domain_box = {
          min: JSON.parse(this.getVal('cfg-domain-min')),
          max: JSON.parse(this.getVal('cfg-domain-max')),
        };
      } catch {
        cfg.domain_box = 'auto';
      }
    } else {
      cfg.domain_box = 'auto';
    }

    const symPlane = parseFloat(this.getVal('cfg-symmetry-plane'));
    cfg.symmetry_plane = isNaN(symPlane) ? 0.0 : symPlane;

    const groundStyle = this.getVal('cfg-ground-style');
    if (groundStyle === 'relative') {
      const gClear = parseFloat(this.getVal('cfg-ground-clearance'));
      cfg.ground_clearance = isNaN(gClear) ? 0.035 : gClear;
      delete cfg.ground_plane;
      delete cfg._ground_clearance;
      delete cfg._ground_plane;
    } else if (groundStyle === 'absolute') {
      const gPlane = parseFloat(this.getVal('cfg-ground-plane'));
      cfg.ground_plane = isNaN(gPlane) ? 0.0 : gPlane;
      delete cfg.ground_clearance;
      delete cfg._ground_clearance;
      delete cfg._ground_plane;
    } else {
      // Style 0 / None (Default in config.json): Touching CAD Bottom
      delete cfg.ground_clearance;
      delete cfg.ground_plane;
      // Preserve commented example keys if they existed in activeConfig
      if (this.activeConfig._ground_comment !== undefined) {
        cfg._ground_comment = this.activeConfig._ground_comment;
      }
      if (this.activeConfig._ground_clearance !== undefined) {
        cfg._ground_clearance = this.activeConfig._ground_clearance;
      }
      if (this.activeConfig._ground_clearance_desc !== undefined) {
        cfg._ground_clearance_desc = this.activeConfig._ground_clearance_desc;
      }
      if (this.activeConfig._ground_plane !== undefined) {
        cfg._ground_plane = this.activeConfig._ground_plane;
      }
      if (this.activeConfig._ground_plane_desc !== undefined) {
        cfg._ground_plane_desc = this.activeConfig._ground_plane_desc;
      }
    }

    cfg.domain_faces = {
      "-x": this.getVal('cfg-face-neg-x'),
      "+x": this.getVal('cfg-face-pos-x'),
      "-y": this.getVal('cfg-face-neg-y'),
      "+y": this.getVal('cfg-face-pos-y'),
      "+z": this.getVal('cfg-face-pos-z'),
      "-z": this.getVal('cfg-face-neg-z'),
    };

    // Parallel
    cfg.parallel = {
      n_procs: parseInt(this.getVal('cfg-parallel-procs'), 10) || 32,
    };

    // SLURM
    const modStr = this.getVal('cfg-slurm-modules');
    const modules = modStr ? modStr.split(',').map((s) => s.trim()).filter(Boolean) : null;

    cfg.slurm = {
      qos: this.getVal('cfg-slurm-qos'),
      partition: this.getVal('cfg-slurm-partition'),
      nodes: 1,
      time: this.getVal('cfg-slurm-time'),
      mem_per_cpu: this.getVal('cfg-slurm-mem'),
      openfoam_module: modules,
      openfoam_source: this.getVal('cfg-slurm-source'),
      use_tmpdir: this.getCheck('cfg-slurm-tmpdir'),
      sync_interval: parseInt(this.getVal('cfg-slurm-sync'), 10) || 15,
    };

    // Overrides handling (clean comment by default, active only if checked)
    const isOverridesEnabled = this.getCheck('chk-enable-overrides');
    if (isOverridesEnabled) {
      cfg.overrides = {
        mesh_params: {
          base_cell_size: parseFloat(this.getVal('cfg-override-basecell')) || 0.10,
          surface_level: [
            parseInt(this.getVal('cfg-override-surf-min'), 10) || 4,
            parseInt(this.getVal('cfg-override-surf-max'), 10) || 5,
          ],
          edge_level: parseInt(this.getVal('cfg-override-edge'), 10) || 6,
          near_wake_level: parseInt(this.getVal('cfg-override-nearwake'), 10) || 3,
          far_wake_level: parseInt(this.getVal('cfg-override-farwake'), 10) || 1,
        },
      };
      delete cfg._comment_overrides;
      delete cfg._optional_overrides_example;
    } else {
      delete cfg.overrides;
      cfg._comment_overrides = "Expert overrides — all fields below have built-in defaults in fidelity presets. Uncomment only if manual tuning is needed.";
      cfg._optional_overrides_example = {
        mesh_params: {
          _base_cell_size: 0.10,
          _surface_level: [4, 5],
          _edge_level: 6,
          _near_wake_level: 3,
          _far_wake_level: 1,
        },
      };
    }

    // Clean up any default dictionary keys so JSON remains minimal and clean
    delete cfg.fluid;
    delete cfg.turbulence;
    delete cfg.solver;
    delete cfg.force_refs;
    delete cfg.layers;

    this.activeConfig = cfg;
    this.syncConfigToJsonDrawer();
    this.updateDomainBoxVisualization();
  }

  syncConfigToJsonDrawer() {
    const editor = document.getElementById('raw-json-editor');
    if (editor && document.activeElement !== editor) {
      editor.value = JSON.stringify(this.activeConfig, null, 4);
      this.setJsonStatus('JSON Valid & Synced', true);
    }
  }

  bindJsonDrawer() {
    const drawer = document.getElementById('json-drawer');
    const toggleBtn = document.getElementById('btn-toggle-json-drawer');
    const closeBtn = document.getElementById('btn-close-drawer');
    const copyBtn = document.getElementById('btn-copy-json');
    const applyBtn = document.getElementById('btn-apply-json');
    const editor = document.getElementById('raw-json-editor');

    toggleBtn?.addEventListener('click', () => drawer?.classList.toggle('open'));
    closeBtn?.addEventListener('click', () => drawer?.classList.remove('open'));

    copyBtn?.addEventListener('click', () => {
      if (editor) {
        navigator.clipboard.writeText(editor.value);
        this.showToast('JSON copied to clipboard', 'info');
      }
    });

    applyBtn?.addEventListener('click', () => this.applyJsonFromDrawer(true));

    // Real-time live auto-sync: automatically update visual form as user edits JSON
    let debounceTimer = null;
    editor?.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        this.applyJsonFromDrawer(false); // live sync without popup toast spam
      }, 250);
    });

    // Immediate sync on blur (e.g. clicking outside or switching focus)
    editor?.addEventListener('blur', () => {
      clearTimeout(debounceTimer);
      this.applyJsonFromDrawer(false);
    });
  }

  applyJsonFromDrawer(showToast = false) {
    const editor = document.getElementById('raw-json-editor');
    if (!editor) return;

    try {
      const parsed = JSON.parse(editor.value);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Config root must be a JSON object');
      }

      this.isSyncingFromJson = true;
      this.activeConfig = parsed;
      this.updateVisualFormFromConfig(parsed);
      this.updateDomainBoxVisualization();
      this.isSyncingFromJson = false;

      this.setJsonStatus('Live Synced with Form', true);
      if (showToast) {
        // Pretty-format valid JSON on manual click
        editor.value = JSON.stringify(parsed, null, 4);
        this.showToast('Visual form updated from JSON', 'success');
      }
    } catch (err) {
      this.isSyncingFromJson = false;
      this.setJsonStatus(`Syntax Error: ${err.message}`, false);
      if (showToast) {
        this.showToast(`Invalid JSON: ${err.message}`, 'error');
      }
    }
  }

  setJsonStatus(text, ok) {
    const el = document.getElementById('json-parse-status');
    if (el) {
      el.textContent = text;
      el.className = `json-status ${ok ? 'ok' : 'error'}`;
    }
  }

  // -------------------------------------------------------------
  // STL Upload & Management
  // -------------------------------------------------------------
  bindSTLUpload() {
    const input = document.getElementById('stl-file-input');
    const placeholder = document.getElementById('viewer-empty-msg');
    const container = document.getElementById('stl-viewer-container');

    input?.addEventListener('change', (e) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        this.handleSTLFiles(Array.from(files));
      }
    });

    // Drag and drop into 3D viewer
    ['dragenter', 'dragover'].forEach((eventName) => {
      container?.addEventListener(eventName, (e) => {
        e.preventDefault();
        placeholder?.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      container?.addEventListener(eventName, (e) => {
        e.preventDefault();
        placeholder?.classList.remove('dragover');
      });
    });

    container?.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        this.handleSTLFiles(Array.from(files));
      }
    });

    // 3D Viewer overlay tool checkboxes
    document.getElementById('chk-show-axes')?.addEventListener('change', (e) => {
      this.viewer.toggleAxes(e.target.checked);
    });
    document.getElementById('chk-show-domain')?.addEventListener('change', (e) => {
      this.viewer.toggleDomain(e.target.checked);
    });
    document.getElementById('chk-show-bounds')?.addEventListener('change', (e) => {
      this.viewer.toggleBounds(e.target.checked);
    });
    document.getElementById('chk-show-ground')?.addEventListener('change', (e) => {
      this.viewer.toggleGround(e.target.checked);
    });
    document.getElementById('chk-show-flow')?.addEventListener('change', (e) => {
      this.viewer.toggleFlow(e.target.checked);
    });

    // Framing buttons: Fit Domain vs Fit Model
    const btnFitDomain = document.getElementById('btn-fit-domain');
    const btnFitModel = document.getElementById('btn-fit-model');

    btnFitDomain?.addEventListener('click', () => {
      this.viewer.fitView('domain');
      btnFitDomain.classList.add('active');
      btnFitModel?.classList.remove('active');
    });

    btnFitModel?.addEventListener('click', () => {
      this.viewer.fitView('model');
      btnFitModel.classList.add('active');
      btnFitDomain?.classList.remove('active');
    });

    // Camera angle presets (Iso, Top, Side, Front)
    document.querySelectorAll('.btn-view-angle').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const angle = e.target.dataset.angle;
        this.viewer.setViewAngle(angle);
      });
    });

    // Maximize / Expand 3D Viewer Area
    const expandBtn = document.getElementById('btn-toggle-expand-viewer');
    const viewerPanel = document.getElementById('viewer-panel');
    if (expandBtn && viewerPanel) {
      expandBtn.addEventListener('click', () => {
        const isMaximized = viewerPanel.classList.toggle('maximized');
        expandBtn.textContent = isMaximized ? 'Collapse' : 'Expand';
        expandBtn.className = isMaximized ? 'btn btn-primary btn-xs' : 'btn btn-secondary btn-xs';
        setTimeout(() => this.viewer.onResize(), 150);
      });
    }
  }

  async autoSymmetryPlaneCenter() {
    let center = null;
    let axisName = 'X';

    // 1. Try local Three.js or cached bounds
    let bounds = this.currentSTLBounds;
    if (!bounds && this.viewer && this.viewer.currentMesh) {
      const geo = this.viewer.currentMesh.geometry;
      if (geo && geo.boundingBox) {
        bounds = {
          min: [geo.boundingBox.min.x, geo.boundingBox.min.y, geo.boundingBox.min.z],
          max: [geo.boundingBox.max.x, geo.boundingBox.max.y, geo.boundingBox.max.z],
        };
      }
    }

    if (bounds && bounds.min && bounds.max) {
      const flowDir = this.activeConfig.flow?.direction || '-z';
      const dfAxis = this.activeConfig.outputs?.downforce_axis || '-y';
      const axisToIdx = { 'x': 0, 'y': 1, 'z': 2 };
      const flowIdx = axisToIdx[flowDir.replace(/^[+-]/, '').toLowerCase()] ?? 2;
      const upIdx = axisToIdx[dfAxis.replace(/^[+-]/, '').toLowerCase()] ?? 1;
      const lateralIdx = [0, 1, 2].find((i) => i !== flowIdx && i !== upIdx) ?? 0;
      axisName = ['X', 'Y', 'Z'][lateralIdx];

      const minVal = bounds.min[lateralIdx];
      const maxVal = bounds.max[lateralIdx];
      center = (minVal + maxVal) / 2.0;
      center = Math.round(center * 10000) / 10000;
      if (Math.abs(center) < 0.0001) center = 0.0;
    } else {
      // 2. Fetch from backend domain-box endpoint
      try {
        const res = await fetch('/api/geometry/domain-box', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ config: this.activeConfig }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.auto_symmetry_plane !== undefined) {
            center = data.auto_symmetry_plane;
            axisName = (data.lateral_axis || 'x').toUpperCase();
          }
        }
      } catch (err) {
        console.warn('Could not derive symmetry plane center:', err);
      }
    }

    if (center === null || isNaN(center)) {
      this.showToast('Could not calculate symmetry center (no geometry loaded)', 'warning');
      return;
    }

    // Apply to input and active config
    this.setVal('cfg-symmetry-plane', center);
    this.activeConfig.symmetry_plane = center;
    this.buildConfigFromVisualForm();

    this.showToast(`Auto Symmetry Plane set to center (${axisName} = ${center} m)`, 'success');
  }

  zeroSymmetryPlane() {
    this.setVal('cfg-symmetry-plane', 0.0);
    this.activeConfig.symmetry_plane = 0.0;
    this.buildConfigFromVisualForm();
    this.showToast('Symmetry Plane set to CAD Origin (0.0 m)', 'info');
  }

  async updateDomainBoxVisualization(autoFit = false) {
    if (!this.viewer) return;
    try {
      const res = await fetch('/api/geometry/domain-box', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: this.activeConfig,
          bounds: this.currentSTLBounds || null,
        }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.domain_box && data.domain_box.min && data.domain_box.max) {
        const sym = this.activeConfig.symmetry_plane !== undefined ? this.activeConfig.symmetry_plane : 0.0;
        const flowDir = this.activeConfig.flow?.direction || '-z';
        this.viewer.updateDomainBox(data.domain_box.min, data.domain_box.max, sym, flowDir);
        if (autoFit) {
          this.viewer.fitView('domain');
          const btnFitDomain = document.getElementById('btn-fit-domain');
          const btnFitModel = document.getElementById('btn-fit-model');
          btnFitDomain?.classList.add('active');
          btnFitModel?.classList.remove('active');
        }
      }
    } catch (err) {
      console.warn('Error updating domain box visualization:', err);
    }
  }

  async loadSTLGeometryFromServer(filename) {
    if (!this.viewer || !filename) return;
    try {
      const res = await fetch(`/api/stl/file/${encodeURIComponent(filename)}`);
      if (!res.ok) return;
      const buffer = await res.arrayBuffer();
      const info = this.viewer.loadSTLFromArrayBuffer(buffer, filename);
      if (info && info.bbox) {
        this.currentSTLBounds = info.bbox;
      }
      await this.updateDomainBoxVisualization(true);
    } catch (err) {
      console.warn('Could not auto-load STL file geometry:', err);
    }
  }

  async handleSTLFiles(files) {
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.stl')) continue;

      // 1. Preview in Three.js locally via FileReader
      const reader = new FileReader();
      reader.onload = (e) => {
        const buffer = e.target.result;
        const info = this.viewer.loadSTLFromArrayBuffer(buffer, file.name);
        if (info && info.bbox) {
          this.currentSTLBounds = info.bbox;
          this.updateDomainBoxVisualization();
        }
      };
      reader.readAsArrayBuffer(file);

      // 2. Upload to server
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch('/api/stl/upload', {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          this.showToast(`Uploaded ${file.name}`, 'success');
          if (!this.activeConfig.stl_files) this.activeConfig.stl_files = [];
          if (!this.activeConfig.stl_files.includes(file.name)) {
            this.activeConfig.stl_files.push(file.name);
          }
          this.renderActiveSTLChips(this.activeConfig.stl_files);
          this.syncConfigToJsonDrawer();
        }
      } catch (err) {
        this.showToast(`Upload failed: ${err.message}`, 'error');
      }
    }
  }

  renderActiveSTLChips(stlList) {
    const container = document.getElementById('stl-chip-list');
    const countBadge = document.getElementById('active-stl-count');
    if (!container) return;

    container.innerHTML = '';
    if (countBadge) countBadge.textContent = `${stlList.length} files`;

    stlList.forEach((filename) => {
      const chip = document.createElement('div');
      chip.className = 'stl-chip active';
      chip.innerHTML = `
        <span>${filename}</span>
        <span class="btn-remove" title="Remove">&times;</span>
      `;
      chip.addEventListener('click', (e) => {
        if (!e.target.classList.contains('btn-remove')) {
          this.loadSTLGeometryFromServer(filename);
        }
      });
      chip.querySelector('.btn-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        this.activeConfig.stl_files = this.activeConfig.stl_files.filter((f) => f !== filename);
        this.renderActiveSTLChips(this.activeConfig.stl_files);
        this.syncConfigToJsonDrawer();
      });
      container.appendChild(chip);
    });
  }

  async loadExistingSTLs() {
    try {
      const res = await fetch('/api/stl/list');
      const stls = await res.json();
      if (stls && stls.length > 0) {
        // If no STL is active, pick the first one
        if (!this.activeConfig.stl_files || this.activeConfig.stl_files.length === 0) {
          this.activeConfig.stl_files = [stls[0].filename];
          this.renderActiveSTLChips(this.activeConfig.stl_files);
          await this.loadSTLGeometryFromServer(stls[0].filename);
        }
      }
    } catch {}
  }

  // -------------------------------------------------------------
  // Template & Config Loading
  // -------------------------------------------------------------
  async loadTemplatesList() {
    try {
      const res = await fetch('/api/config/templates');
      const templates = await res.json();
      const select = document.getElementById('select-template');
      if (select && templates.length > 0) {
        select.innerHTML = '';
        templates.forEach((t) => {
          const opt = document.createElement('option');
          opt.value = t.filename;
          opt.textContent = `configs/${t.filename}`;
          select.appendChild(opt);
        });
      }
    } catch {}
  }

  async loadConfigFile(filename, quiet = false) {
    try {
      const res = await fetch(`/api/config/load-file?filename=${encodeURIComponent(filename)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      this.activeConfig = data.raw_config;
      this.updateVisualFormFromConfig(this.activeConfig);
      this.syncConfigToJsonDrawer();
      const select = document.getElementById('select-template');
      if (select) select.value = filename;

      if (this.activeConfig.stl_files && this.activeConfig.stl_files.length > 0) {
        this.renderActiveSTLChips(this.activeConfig.stl_files);
        await this.loadSTLGeometryFromServer(this.activeConfig.stl_files[0]);
      } else {
        await this.updateDomainBoxVisualization(true);
      }

      if (!quiet) this.showToast(`Loaded template ${filename}`, 'success');
    } catch (err) {
      if (!quiet) this.showToast(`Failed to load config: ${err.message}`, 'error');
    }
  }

  // -------------------------------------------------------------
  // Validation & Case Submission
  // -------------------------------------------------------------
  async validateCurrentConfig() {
    this.buildConfigFromVisualForm();
    try {
      const res = await fetch('/api/case/generate-and-submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: this.activeConfig,
          upload_to_cluster: false,
          generate_remotely: false,
          submit_slurm: false,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Validation failed');
      this.showToast('Configuration valid. Ready to generate.', 'success');
      if (data.warnings && data.warnings.length > 0) {
        data.warnings.forEach((w) => this.showToast(w, 'info'));
      }
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  }

  async saveCurrentConfig(submitToCluster = false) {
    this.buildConfigFromVisualForm();

    if (submitToCluster && !this.clusterConnected) {
      this.showToast('Please connect to the cluster via SSH first!', 'error');
      this.openSSHModal();
      return;
    }

    const btnSubmit = document.getElementById('btn-submit-case');
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.textContent = submitToCluster ? 'Submitting to Cluster...' : 'Saving...';
    }

    try {
      const res = await fetch('/api/case/generate-and-submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: this.activeConfig,
          upload_to_cluster: submitToCluster,
          generate_remotely: submitToCluster,
          submit_slurm: submitToCluster,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Request failed');

      if (submitToCluster) {
        const slurmRes = data.cluster_actions?.slurm_submit;
        if (slurmRes && slurmRes.job_id) {
          this.showToast(`Simulation submitted. SLURM Job ID: ${slurmRes.job_id}`, 'success');
        } else {
          this.showToast(`Generated case ${data.case_name} on cluster!`, 'success');
        }
        // Switch to Telemetry tab to monitor
        document.getElementById('tab-btn-telemetry')?.click();
        this.addTelemetryCase(data.case_name);
        this.refreshQueue();
      } else {
        this.showToast(`Config saved locally for ${data.case_name}`, 'success');
      }
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'error');
    } finally {
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.textContent = 'Launch Simulation on Cluster';
      }
    }
  }

  // -------------------------------------------------------------
  // SSH Cluster Connection Modal
  // -------------------------------------------------------------
  bindSSHModal() {
    const modal = document.getElementById('ssh-modal');
    const openBtn = document.getElementById('btn-open-ssh-modal');
    const closeBtn = document.getElementById('btn-close-ssh-modal');
    const cancelBtn = document.getElementById('btn-cancel-ssh');
    const backdrop = document.getElementById('modal-backdrop');
    const connectSubmitBtn = document.getElementById('btn-connect-ssh-submit');
    const reconnectBtn = document.getElementById('btn-reconnect-ssh');

    openBtn?.addEventListener('click', () => this.openSSHModal());
    closeBtn?.addEventListener('click', () => this.closeSSHModal());
    cancelBtn?.addEventListener('click', () => this.closeSSHModal());
    backdrop?.addEventListener('click', () => this.closeSSHModal());
    reconnectBtn?.addEventListener('click', () => this.openSSHModal());

    connectSubmitBtn?.addEventListener('click', () => this.submitSSHConnect());
  }

  async loadLocalClusterConfig() {
    let cfg = null;

    // 1. First check browser localStorage for credentials saved on this machine
    try {
      const stored = localStorage.getItem('cfd_cluster_config');
      if (stored) {
        cfg = JSON.parse(stored);
      }
    } catch {}

    // 2. Fallback or sync with server-side saved config (~/.cfd_gen_cluster.json)
    if (!cfg || !cfg.host) {
      try {
        const res = await fetch('/api/cluster/saved-config');
        if (res.ok) {
          const serverCfg = await res.json();
          if (serverCfg && serverCfg.host) {
            cfg = serverCfg;
          }
        }
      } catch {}
    }

    if (cfg) {
      if (cfg.host) this.setValText('disp-cluster-host', cfg.host);
      if (cfg.username) this.setValText('disp-cluster-user', cfg.username);
      if (cfg.remote_repo_path) this.setValText('disp-remote-repo', cfg.remote_repo_path);

      this.setVal('ssh-host', cfg.host || '');
      this.setVal('ssh-username', cfg.username || '');
      this.setVal('ssh-remotepath', cfg.remote_repo_path || '');
      this.setVal('ssh-keypath', cfg.key_path || '');
      if (cfg.saved_password) {
        this.setVal('ssh-password', cfg.saved_password);
      }
    } else {
      this.setValText('disp-cluster-host', 'Not Configured');
      this.setValText('disp-cluster-user', '--');
      this.setValText('disp-remote-repo', '--');
    }
    return cfg;
  }

  async openSSHModal() {
    const modal = document.getElementById('ssh-modal');
    if (!modal) return;

    // Load saved settings from local storage or server
    await this.loadLocalClusterConfig();

    document.getElementById('ssh-error-alert').style.display = 'none';
    document.getElementById('ssh-success-alert').style.display = 'none';
    modal.style.display = 'flex';
  }

  closeSSHModal() {
    const modal = document.getElementById('ssh-modal');
    if (modal) modal.style.display = 'none';
  }

  async submitSSHConnect() {
    const host = this.getVal('ssh-host');
    const username = this.getVal('ssh-username');
    const password = this.getVal('ssh-password');
    const keyPath = this.getVal('ssh-keypath');
    const remoteRepo = this.getVal('ssh-remotepath');
    const savePw = this.getCheck('ssh-save-pw');

    const errAlert = document.getElementById('ssh-error-alert');
    const succAlert = document.getElementById('ssh-success-alert');
    const submitBtn = document.getElementById('btn-connect-ssh-submit');

    errAlert.style.display = 'none';
    succAlert.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Connecting...';

    // Persist credentials locally in localStorage
    try {
      const localCfg = {
        host,
        username,
        key_path: keyPath || '',
        remote_repo_path: remoteRepo,
        saved_password: savePw ? (password || '') : '',
        save_password: savePw,
      };
      localStorage.setItem('cfd_cluster_config', JSON.stringify(localCfg));
    } catch {}

    // Update display metrics immediately
    if (host) this.setValText('disp-cluster-host', host);
    if (username) this.setValText('disp-cluster-user', username);
    if (remoteRepo) this.setValText('disp-remote-repo', remoteRepo);

    try {
      const res = await fetch('/api/cluster/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host,
          username,
          password: password || null,
          key_path: keyPath || null,
          remote_repo_path: remoteRepo,
          save_password: savePw,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Connection failed');

      succAlert.textContent = `Connected to ${data.remote_host || host}! Python: ${data.remote_python}`;
      succAlert.style.display = 'block';
      this.updateClusterStatusBadge(true, username, host);
      this.showToast(`Connected to ${host}`, 'success');

      setTimeout(() => {
        this.closeSSHModal();
        this.refreshQueue();
      }, 1000);
    } catch (err) {
      errAlert.textContent = `Connection error: ${err.message}`;
      errAlert.style.display = 'block';
      this.updateClusterStatusBadge(false);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Connect & Test';
    }
  }

  async checkClusterStatus() {
    try {
      const res = await fetch('/api/cluster/status');
      const data = await res.json();
      this.updateClusterStatusBadge(data.connected, data.username, data.host);
      if (data.connected) {
        this.renderQueueTable(data.active_jobs || []);
      }
    } catch {
      this.updateClusterStatusBadge(false);
    }
  }

  updateClusterStatusBadge(connected, user = '', host = '') {
    this.clusterConnected = connected;
    const badge = document.getElementById('cluster-status-badge');
    if (!badge) return;

    const dot = badge.querySelector('.status-dot');
    const text = badge.querySelector('.status-text');

    if (connected) {
      dot.className = 'status-dot connected';
      text.textContent = `${user}@${host.split('.')[0]}`;
      if (host) this.setValText('disp-cluster-host', host);
      if (user) this.setValText('disp-cluster-user', user);
      this.setValText('disp-slurm-status', 'Active & Ready');
    } else {
      dot.className = 'status-dot disconnected';
      text.textContent = 'Disconnected';
      this.setValText('disp-slurm-status', 'Disconnected');
    }
  }

  // -------------------------------------------------------------
  // SLURM Queue Monitoring
  // -------------------------------------------------------------
  async refreshQueue() {
    if (!this.clusterConnected) return;
    try {
      const res = await fetch('/api/cluster/status');
      const data = await res.json();
      this.renderQueueTable(data.active_jobs || []);
    } catch {}
  }

  renderQueueTable(jobs) {
    const tbody = document.getElementById('slurm-queue-tbody');
    if (!tbody) return;

    if (!jobs || jobs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No active cluster jobs found.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    jobs.forEach((job) => {
      const tr = document.createElement('tr');
      const isRunning = job.state === 'RUNNING' || job.state === 'R';
      const stateBadge = isRunning
        ? '<span class="tag-running">RUNNING</span>'
        : `<span class="tag-pending">${job.state}</span>`;

      tr.innerHTML = `
        <td><strong>${job.job_id}</strong></td>
        <td>${job.name}</td>
        <td>${job.partition}</td>
        <td>${stateBadge}</td>
        <td>${job.time_used}</td>
        <td>${job.time_limit}</td>
        <td>${job.nodes}</td>
        <td><button class="btn btn-outline btn-xs btn-cancel-job" data-id="${job.job_id}">Cancel</button></td>
      `;

      tr.querySelector('.btn-cancel-job').addEventListener('click', () => {
        this.cancelJob(job.job_id);
      });

      tbody.appendChild(tr);
    });
  }

  async cancelJob(jobId) {
    if (!confirm(`Cancel SLURM Job ${jobId}?`)) return;
    try {
      const res = await fetch('/api/case/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId }),
      });
      const data = await res.json();
      if (data.success) {
        this.showToast(`Cancelled job ${jobId}`, 'info');
        this.refreshQueue();
      } else {
        this.showToast(`Could not cancel: ${data.error}`, 'error');
      }
    } catch (err) {
      this.showToast(`Cancel error: ${err.message}`, 'error');
    }
  }

  // -------------------------------------------------------------
  // Live Telemetry & Console Tail
  // -------------------------------------------------------------
  bindTelemetryEvents() {
    document.getElementById('btn-refresh-telemetry')?.addEventListener('click', () => this.pollTelemetry());
    document.getElementById('telemetry-case-select')?.addEventListener('change', () => this.pollTelemetry());
    document.getElementById('btn-tail-log')?.addEventListener('click', () => this.fetchLogTail());
    document.getElementById('select-log-type')?.addEventListener('change', () => this.fetchLogTail());
  }

  addTelemetryCase(caseName) {
    const select = document.getElementById('telemetry-case-select');
    if (!select) return;

    let exists = false;
    for (const opt of select.options) {
      if (opt.value === caseName) {
        exists = true;
        break;
      }
    }
    if (!exists) {
      const opt = document.createElement('option');
      opt.value = caseName;
      opt.textContent = caseName;
      select.appendChild(opt);
    }
    select.value = caseName;
  }

  async pollTelemetry() {
    const select = document.getElementById('telemetry-case-select');
    const caseName = select ? select.value : '';
    if (!caseName) return;

    // 1. Fetch Forces
    try {
      const res = await fetch(`/api/telemetry/forces?case_name=${encodeURIComponent(caseName)}`);
      const data = await res.json();

      if (data.has_data) {
        this.setValText('kpi-downforce', data.downforce_avg);
        this.setValText('kpi-downforce-variation', `±${data.downforce_pct}%`);
        this.setValText('kpi-drag', data.drag_avg);
        this.setValText('kpi-drag-variation', `±${data.drag_pct}%`);
        this.setValText('kpi-ld', data.ld_ratio);
        this.setValText('kpi-iter', data.latest_iteration);

        const pill = document.getElementById('telemetry-convergence-pill');
        if (pill) {
          if (data.converged) {
            pill.className = 'convergence-status-pill converged';
            pill.querySelector('.pill-text').textContent = 'CONVERGED';
          } else {
            pill.className = 'convergence-status-pill running';
            pill.querySelector('.pill-text').textContent = `Solving (Iter ${data.latest_iteration})`;
          }
        }

        if (this.charts && data.series) {
          this.charts.updateForces(data.series);
        }
      }
    } catch {}

    // 2. Fetch Residuals
    try {
      const res = await fetch(`/api/telemetry/residuals?case_name=${encodeURIComponent(caseName)}`);
      const resData = await res.json();
      if (resData.has_data && this.charts) {
        this.charts.updateResiduals(resData.iterations, resData.residuals);
      }
    } catch {}

    // 3. Tail log
    this.fetchLogTail();
  }

  async fetchLogTail() {
    const select = document.getElementById('telemetry-case-select');
    const logType = document.getElementById('select-log-type')?.value || 'simpleFoam';
    const caseName = select ? select.value : '';
    if (!caseName) return;

    try {
      const res = await fetch(`/api/telemetry/logs?case_name=${encodeURIComponent(caseName)}&log_type=${logType}&lines=60`);
      const data = await res.json();
      const consoleBox = document.getElementById('console-output');
      if (consoleBox) {
        consoleBox.textContent = data.content || 'Log file empty.';
        consoleBox.scrollTop = consoleBox.scrollHeight;
      }
    } catch {}
  }

  // -------------------------------------------------------------
  // Cases Archive
  // -------------------------------------------------------------
  async loadCasesArchive() {
    const tbody = document.getElementById('archive-tbody');
    const select = document.getElementById('telemetry-case-select');
    if (!tbody) return;

    try {
      const res = await fetch('/api/cases');
      const cases = await res.json();

      if (!cases || cases.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No simulation cases found.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      if (select && select.options.length <= 1) {
        cases.forEach((c) => {
          const opt = document.createElement('option');
          opt.value = c.name;
          opt.textContent = `${c.name} (${c.location})`;
          select.appendChild(opt);
        });
      }

      cases.forEach((c) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${c.name}</strong></td>
          <td><span class="badge">${c.location}</span></td>
          <td>${c.modified}</td>
          <td>
            <button class="btn btn-outline btn-xs btn-inspect-case" data-name="${c.name}">Telemetry</button>
          </td>
        `;

        tr.querySelector('.btn-inspect-case').addEventListener('click', () => {
          document.getElementById('tab-btn-telemetry')?.click();
          this.addTelemetryCase(c.name);
          this.pollTelemetry();
        });

        tbody.appendChild(tr);
      });
    } catch {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Failed to load cases.</td></tr>';
    }
  }

  // -------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------
  getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
  }

  setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val;
  }

  setValText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  getCheck(id) {
    const el = document.getElementById(id);
    return el ? el.checked : false;
  }

  setCheck(id, checked) {
    const el = document.getElementById(id);
    if (el) el.checked = checked;
  }

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ';
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

// Instantiate on load
window.addEventListener('DOMContentLoaded', () => {
  window.app = new CFDApp();
});
