/**
 * 3D Geometry & Wind Tunnel Inspector using Three.js
 */

class STLViewer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.currentMesh = null;
    this.bboxHelper = null;
    this.domainBoxGroup = null;
    this.groundGrid = null;
    this.flowArrow = null;

    this.showBounds = true;
    this.showDomain = true;
    this.showGround = true;
    this.showFlow = true;

    this.currentFocusTarget = 'domain'; // 'domain' or 'model'
    this.domainMin = null;
    this.domainMax = null;
    this.flowDirection = '-z';
    this.symPlaneCoord = null;

    this.init();
  }

  init() {
    if (typeof THREE === 'undefined') {
      console.warn('Three.js not loaded. 3D viewer unavailable.');
      return;
    }

    const width = this.container.clientWidth || 600;
    const height = this.container.clientHeight || 480;

    // 1. Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x080c14);

    // 2. Camera (Wide view distance so 50m domain fits comfortably)
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.05, 2000);
    this.camera.position.set(15, 12, 28);

    // 3. Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;

    // Clean container and attach
    const emptyMsg = document.getElementById('viewer-empty-msg');
    if (emptyMsg) emptyMsg.style.display = 'none';
    this.container.appendChild(this.renderer.domElement);

    // 4. Controls
    if (typeof THREE.OrbitControls !== 'undefined') {
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.maxDistance = 1500;
    }

    // 5. Lighting (Studio Aero lighting)
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x1e293b, 0.9);
    this.scene.add(hemiLight);

    const dirLight1 = new THREE.DirectionalLight(0x00d2ff, 0.7);
    dirLight1.position.set(10, 20, 15);
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.6);
    dirLight2.position.set(-10, -10, -15);
    this.scene.add(dirLight2);

    // 6. Ground Grid (Spans 60m to encompass complete wind tunnel)
    this.createGroundGrid();

    // 7. Flow Vector Arrow (default -Z)
    this.updateFlowArrow(new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, 1.2, 8.0), 3.0);

    // Handle Resize (window and container observer)
    window.addEventListener('resize', () => this.onResize());
    if (window.ResizeObserver && this.container) {
      this.resizeObserver = new ResizeObserver(() => this.onResize());
      this.resizeObserver.observe(this.container);
    }

    // Animation Loop
    this.animate();
  }

  createGroundGrid() {
    if (this.groundGrid) this.scene.remove(this.groundGrid);
    this.groundGrid = new THREE.GridHelper(60, 60, 0x00d2ff, 0x1e293b);
    this.groundGrid.position.set(0, 0, 0);
    this.groundGrid.visible = this.showGround;
    this.scene.add(this.groundGrid);
  }

  createCanvasTextSprite(text, color = '#00f0ff', bgColor = 'rgba(15, 23, 42, 0.88)') {
    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 80;
    const ctx = canvas.getContext('2d');

    // Rounded background container
    ctx.fillStyle = bgColor;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(4, 4, 312, 72, 12);
    } else {
      ctx.rect(4, 4, 312, 72);
    }
    ctx.fill();

    // Border
    ctx.strokeStyle = color;
    ctx.lineWidth = 4;
    ctx.stroke();

    // Typography
    ctx.font = 'bold 24px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 160, 40);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(3.8, 0.95, 1.0);
    return sprite;
  }

  parseFlowDirectionVector(dirStr = '-z') {
    const s = (dirStr || '-z').trim().toLowerCase();
    const sign = s.startsWith('-') ? -1 : 1;
    const axis = s.replace(/[^xyz]/g, '') || 'z';
    return new THREE.Vector3(
      axis === 'x' ? sign : 0,
      axis === 'y' ? sign : 0,
      axis === 'z' ? sign : 0
    );
  }

  updateFlowArrow(direction = new THREE.Vector3(0, 0, -1), origin = new THREE.Vector3(0, 1.2, 8.0), length = 3.0) {
    if (this.flowArrow) this.scene.remove(this.flowArrow);
    const color = 0x00e5ff;
    const dirNorm = direction.clone().normalize();
    this.flowArrow = new THREE.ArrowHelper(dirNorm, origin, length, color, length * 0.25, length * 0.15);
    this.flowArrow.visible = this.showFlow;
    this.scene.add(this.flowArrow);
  }

  loadSTLFromArrayBuffer(buffer, filename = 'geometry.stl') {
    if (typeof THREE.STLLoader === 'undefined') {
      console.error('STLLoader not available.');
      return;
    }

    const loader = new THREE.STLLoader();
    try {
      const geometry = loader.parse(buffer);
      geometry.computeVertexNormals();

      if (this.currentMesh) {
        this.scene.remove(this.currentMesh);
        if (this.currentMesh.geometry) this.currentMesh.geometry.dispose();
      }
      if (this.bboxHelper) {
        this.scene.remove(this.bboxHelper);
        this.bboxHelper = null;
      }

      // Material: Sleek aerodynamic metallic finish
      const material = new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        metalness: 0.35,
        roughness: 0.35,
        flatShading: false,
      });

      this.currentMesh = new THREE.Mesh(geometry, material);
      this.scene.add(this.currentMesh);

      // Compute bounding box
      geometry.computeBoundingBox();
      const bbox = geometry.boundingBox;
      const size = new THREE.Vector3();
      bbox.getSize(size);

      // Add Model Bounding Box Helper (Warm Golden Amber for instant visual distinction)
      this.bboxHelper = new THREE.Box3Helper(bbox, 0xf59e0b);
      this.bboxHelper.visible = this.showBounds;
      this.scene.add(this.bboxHelper);

      // Check scale warning (mm vs m)
      const maxDim = Math.max(size.x, size.y, size.z);
      const warnEl = document.getElementById('scale-warning');
      if (warnEl) {
        warnEl.style.display = maxDim > 20.0 ? 'block' : 'none';
      }

      // Camera auto-framing
      if (this.domainMin && this.domainMax) {
        this.fitView('domain');
      } else {
        this.fitView('model');
      }

      return {
        bbox: {
          min: [bbox.min.x, bbox.min.y, bbox.min.z],
          max: [bbox.max.x, bbox.max.y, bbox.max.z],
        },
        size: [size.x, size.y, size.z],
        isLikelyMM: maxDim > 20.0,
      };
    } catch (err) {
      console.error('Failed to parse STL:', err);
      return null;
    }
  }

  fitView(target = 'domain') {
    this.currentFocusTarget = target;
    const fov = this.camera.fov * (Math.PI / 180);

    if (target === 'domain' && this.domainMin && this.domainMax) {
      const minVec = new THREE.Vector3(...this.domainMin);
      const maxVec = new THREE.Vector3(...this.domainMax);
      const center = new THREE.Vector3().addVectors(minVec, maxVec).multiplyScalar(0.5);
      const size = new THREE.Vector3().subVectors(maxVec, minVec);

      const maxDim = Math.max(size.x, size.y, size.z);
      // Framing distance with ample padding so all 40m tunnel boundaries and badges are visible
      const dist = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 1.35;

      this.camera.position.set(center.x + dist * 0.75, center.y + dist * 0.48, center.z + dist * 0.85);
      this.camera.lookAt(center);

      if (this.controls) {
        this.controls.target.copy(center);
        this.controls.update();
      }
    } else if (this.currentMesh) {
      const bbox = this.currentMesh.geometry.boundingBox;
      const center = new THREE.Vector3();
      const size = new THREE.Vector3();
      bbox.getCenter(center);
      bbox.getSize(size);

      const maxDim = Math.max(size.x, size.y, size.z);
      const dist = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 1.8;

      this.camera.position.set(center.x + dist * 0.8, center.y + dist * 0.6, center.z + dist);
      this.camera.lookAt(center);

      if (this.controls) {
        this.controls.target.copy(center);
        this.controls.update();
      }
    } else {
      this.camera.position.set(15, 12, 28);
      this.camera.lookAt(0, 0, 0);
      if (this.controls) {
        this.controls.target.set(0, 0, 0);
        this.controls.update();
      }
    }
  }

  resetCamera(target = null) {
    this.fitView(target || this.currentFocusTarget || (this.domainMin ? 'domain' : 'model'));
  }

  setViewAngle(angle, target = null) {
    const activeTarget = target || this.currentFocusTarget || (this.domainMin ? 'domain' : 'model');
    const fov = this.camera.fov * (Math.PI / 180);

    let center = new THREE.Vector3(0, 0, 0);
    let dist = 20;

    if (activeTarget === 'domain' && this.domainMin && this.domainMax) {
      const minVec = new THREE.Vector3(...this.domainMin);
      const maxVec = new THREE.Vector3(...this.domainMax);
      center = new THREE.Vector3().addVectors(minVec, maxVec).multiplyScalar(0.5);
      const size = new THREE.Vector3().subVectors(maxVec, minVec);
      const maxDim = Math.max(size.x, size.y, size.z);
      dist = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 1.35;
    } else if (this.currentMesh) {
      const bbox = this.currentMesh.geometry.boundingBox;
      bbox.getCenter(center);
      const size = new THREE.Vector3();
      bbox.getSize(size);
      const maxDim = Math.max(size.x, size.y, size.z);
      dist = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 1.8;
    }

    if (angle === 'top') {
      this.camera.position.set(center.x, center.y + dist * 1.25, center.z + 0.001);
    } else if (angle === 'side') {
      this.camera.position.set(center.x + dist * 1.25, center.y, center.z);
    } else if (angle === 'front') {
      this.camera.position.set(center.x, center.y, center.z + dist * 1.25);
    } else { // iso
      this.camera.position.set(center.x + dist * 0.75, center.y + dist * 0.48, center.z + dist * 0.85);
    }

    this.camera.lookAt(center);
    if (this.controls) {
      this.controls.target.copy(center);
      this.controls.update();
    }
  }

  updateDomainBox(domainMin, domainMax, symPlane = null, flowDirection = '-z') {
    if (this.domainBoxGroup) {
      this.scene.remove(this.domainBoxGroup);
      this.domainBoxGroup = null;
    }

    if (!domainMin || !domainMax) return;

    this.domainMin = domainMin;
    this.domainMax = domainMax;
    this.symPlaneCoord = symPlane;
    this.flowDirection = flowDirection || '-z';

    this.domainBoxGroup = new THREE.Group();

    const minVec = new THREE.Vector3(domainMin[0], domainMin[1], domainMin[2]);
    const maxVec = new THREE.Vector3(domainMax[0], domainMax[1], domainMax[2]);
    const box3 = new THREE.Box3(minVec, maxVec);

    const size = new THREE.Vector3().subVectors(maxVec, minVec);
    const center = new THREE.Vector3().addVectors(minVec, maxVec).multiplyScalar(0.5);

    // 1. Vibrant Neon Cyan Domain Wireframe Cage
    const wireHelper = new THREE.Box3Helper(box3, 0x00f0ff);
    this.domainBoxGroup.add(wireHelper);

    // 2. Corner Accent Spheres (Emphasize domain box vertices clearly in 3D)
    const sphereRadius = Math.max(0.08, Math.min(size.x, size.y, size.z) * 0.018);
    const sphereGeo = new THREE.SphereGeometry(sphereRadius, 10, 10);
    const sphereMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const corners = [
      new THREE.Vector3(minVec.x, minVec.y, minVec.z),
      new THREE.Vector3(maxVec.x, minVec.y, minVec.z),
      new THREE.Vector3(minVec.x, maxVec.y, minVec.z),
      new THREE.Vector3(maxVec.x, maxVec.y, minVec.z),
      new THREE.Vector3(minVec.x, minVec.y, maxVec.z),
      new THREE.Vector3(maxVec.x, minVec.y, maxVec.z),
      new THREE.Vector3(minVec.x, maxVec.y, maxVec.z),
      new THREE.Vector3(maxVec.x, maxVec.y, maxVec.z),
    ];
    corners.forEach((c) => {
      const sp = new THREE.Mesh(sphereGeo, sphereMat);
      sp.position.copy(c);
      this.domainBoxGroup.add(sp);
    });

    // 3. Translucent Wind Tunnel Enclosure Volume (double-sided so never back-culled)
    const boxGeo = new THREE.BoxGeometry(size.x, size.y, size.z);
    const boxMat = new THREE.MeshBasicMaterial({
      color: 0x0284c7,
      transparent: true,
      opacity: 0.08,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const boxMesh = new THREE.Mesh(boxGeo, boxMat);
    boxMesh.position.copy(center);
    this.domainBoxGroup.add(boxMesh);

    // 4. Dedicated Inlet Face (Electric Blue with badge)
    const isInletAtMaxZ = this.flowDirection.includes('-z');
    const inletZ = isInletAtMaxZ ? maxVec.z : minVec.z;
    const outletZ = isInletAtMaxZ ? minVec.z : maxVec.z;

    const inletPlaneGeo = new THREE.PlaneGeometry(size.x, size.y);
    const inletMat = new THREE.MeshBasicMaterial({
      color: 0x0284c7,
      transparent: true,
      opacity: 0.28,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const inletMesh = new THREE.Mesh(inletPlaneGeo, inletMat);
    inletMesh.position.set(center.x, center.y, inletZ);
    this.domainBoxGroup.add(inletMesh);

    const inletBadge = this.createCanvasTextSprite('INLET  ➔', '#00f0ff', 'rgba(15, 23, 42, 0.9)');
    inletBadge.position.set(center.x, center.y, inletZ + (isInletAtMaxZ ? 0.2 : -0.2));
    this.domainBoxGroup.add(inletBadge);

    // 5. Dedicated Outlet Face (Warm Orange with badge)
    const outletPlaneGeo = new THREE.PlaneGeometry(size.x, size.y);
    const outletMat = new THREE.MeshBasicMaterial({
      color: 0xea580c,
      transparent: true,
      opacity: 0.28,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const outletMesh = new THREE.Mesh(outletPlaneGeo, outletMat);
    outletMesh.position.set(center.x, center.y, outletZ);
    this.domainBoxGroup.add(outletMesh);

    const outletBadge = this.createCanvasTextSprite('➔  OUTLET', '#f97316', 'rgba(30, 20, 15, 0.9)');
    outletBadge.position.set(center.x, center.y, outletZ + (isInletAtMaxZ ? -0.2 : 0.2));
    this.domainBoxGroup.add(outletBadge);

    // 6. Ground Face (Dark road surface at domainMin.y)
    const groundPlaneGeo = new THREE.PlaneGeometry(size.x, size.z);
    const groundMat = new THREE.MeshBasicMaterial({
      color: 0x0f172a,
      transparent: true,
      opacity: 0.65,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const groundMesh = new THREE.Mesh(groundPlaneGeo, groundMat);
    groundMesh.rotation.x = -Math.PI / 2;
    groundMesh.position.set(center.x, minVec.y, center.z);
    this.domainBoxGroup.add(groundMesh);

    // Update ground grid position to sit flush with wind tunnel floor
    if (this.groundGrid) {
      this.groundGrid.position.set(center.x, minVec.y, center.z);
    }

    // 7. Symmetry Plane Indicator
    if (symPlane !== null && symPlane !== undefined && isFinite(symPlane)) {
      const symGeo = new THREE.PlaneGeometry(size.z, size.y);
      const symMat = new THREE.MeshBasicMaterial({
        color: 0x06b6d4,
        transparent: true,
        opacity: 0.22,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const symMesh = new THREE.Mesh(symGeo, symMat);
      symMesh.rotation.y = Math.PI / 2;
      symMesh.position.set(symPlane, center.y, center.z);
      this.domainBoxGroup.add(symMesh);

      const symBadge = this.createCanvasTextSprite(`SYMMETRY (${symPlane}m)`, '#38bdf8', 'rgba(15, 23, 42, 0.85)');
      symBadge.position.set(symPlane, maxVec.y - 0.4, center.z);
      this.domainBoxGroup.add(symBadge);
    }

    // 8. Update Flow Arrow position to point into wind tunnel from inlet
    const flowOrigin = new THREE.Vector3(center.x, center.y, isInletAtMaxZ ? maxVec.z - 0.6 : minVec.z + 0.6);
    const flowDirVec = this.parseFlowDirectionVector(this.flowDirection);
    this.updateFlowArrow(flowDirVec, flowOrigin, Math.min(3.5, size.z * 0.12));

    this.domainBoxGroup.visible = this.showDomain;
    this.scene.add(this.domainBoxGroup);

    // Update Dimensions in UI
    const dimsBadge = document.getElementById('viewer-domain-badge');
    const dimsText = document.getElementById('domain-dims-text');
    if (dimsBadge && dimsText) {
      dimsText.textContent = `${size.x.toFixed(2)}m (W) × ${size.y.toFixed(2)}m (H) × ${size.z.toFixed(2)}m (L)`;
      dimsBadge.style.display = 'flex';
    }
  }

  toggleDomain(show) {
    this.showDomain = show;
    if (this.domainBoxGroup) this.domainBoxGroup.visible = show;
    const badge = document.getElementById('viewer-domain-badge');
    if (badge && !show) badge.style.display = 'none';
    else if (badge && show && this.domainMin) badge.style.display = 'flex';
  }

  toggleBounds(show) {
    this.showBounds = show;
    if (this.bboxHelper) this.bboxHelper.visible = show;
  }

  toggleGround(show) {
    this.showGround = show;
    if (this.groundGrid) this.groundGrid.visible = show;
  }

  toggleFlow(show) {
    this.showFlow = show;
    if (this.flowArrow) this.flowArrow.visible = show;
  }

  onResize() {
    if (!this.container || !this.renderer || !this.camera) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (!width || !height || width <= 0 || height <= 0) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    if (this.controls) this.controls.update();
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }
}

window.STLViewer = STLViewer;
