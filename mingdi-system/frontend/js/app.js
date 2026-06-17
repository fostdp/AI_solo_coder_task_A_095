const API_BASE = "http://localhost:8000/api";

let scene, camera, renderer, controls;
let arrowGroup = null;
let streamlines = [];
let soundFieldMesh = null;
let animationId = null;
let currentArrow = "MD-001";
let currentView = "3d";

let currentData = {
    velocity: 65,
    rotation_speed: 100,
    altitude: 50,
    pitch: 0.3,
    whistle_frequency: 1500,
    sound_pressure_level: 85,
    estimated_range: 200,
    reynolds_number: 30000,
    drag_force: 0.15,
    lift_force: 0.08,
    drag_coefficient: 0.08,
    lift_coefficient: 0.15,
    moment: 0.02,
    strouhal_number: 0.2,
    propagation_distance: 500
};

function init() {
    const canvas = document.getElementById('three-canvas');
    const container = canvas.parentElement;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x050810);
    scene.fog = new THREE.Fog(0x050810, 20, 60);

    camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.set(8, 4, 10);

    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    addLights();
    createGround();
    createArrow();
    createStreamlines();
    createSoundField();

    window.addEventListener('resize', onWindowResize);
    setupUI();

    animate();

    setInterval(fetchData, 2000);
    fetchConfig();
    fetchData();
}

function addLights() {
    const ambient = new THREE.AmbientLight(0x404060, 0.5);
    scene.add(ambient);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1);
    dirLight.position.set(10, 20, 10);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    scene.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0x6688ff, 0.3);
    fillLight.position.set(-10, 5, -10);
    scene.add(fillLight);
}

function createGround() {
    const groundGeo = new THREE.PlaneGeometry(50, 50, 50, 50);
    const groundMat = new THREE.MeshStandardMaterial({
        color: 0x1a2338,
        roughness: 0.8,
        metalness: 0.2,
        wireframe: false
    });

    const positions = groundGeo.attributes.position;
    for (let i = 0; i < positions.count; i++) {
        const x = positions.getX(i);
        const z = positions.getZ(i);
        const y = Math.sin(x * 0.2) * 0.1 + Math.cos(z * 0.2) * 0.1;
        positions.setY(i, y);
    }
    groundGeo.computeVertexNormals();

    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -2;
    ground.receiveShadow = true;
    scene.add(ground);

    const gridHelper = new THREE.GridHelper(50, 50, 0x2a3a5c, 0x1a2338);
    gridHelper.position.y = -1.99;
    scene.add(gridHelper);
}

function createArrow() {
    arrowGroup = new THREE.Group();

    const arrowLength = 4;
    const shaftRadius = 0.06;
    const tipLength = 0.8;

    const shaftGeo = new THREE.CylinderGeometry(shaftRadius, shaftRadius, arrowLength - tipLength, 16);
    const shaftMat = new THREE.MeshStandardMaterial({
        color: 0xd4a574,
        roughness: 0.6,
        metalness: 0.3
    });
    const shaft = new THREE.Mesh(shaftGeo, shaftMat);
    shaft.position.y = (arrowLength - tipLength) / 2 - arrowLength / 2 + tipLength / 2;
    shaft.castShadow = true;
    shaft.receiveShadow = true;
    arrowGroup.add(shaft);

    const tipGeo = new THREE.ConeGeometry(shaftRadius * 1.5, tipLength, 16);
    const tipMat = new THREE.MeshStandardMaterial({
        color: 0x8b7355,
        roughness: 0.4,
        metalness: 0.6
    });
    const tip = new THREE.Mesh(tipGeo, tipMat);
    tip.position.y = (arrowLength - tipLength) / 2;
    tip.castShadow = true;
    arrowGroup.add(tip);

    const whistleGeo = new THREE.CylinderGeometry(0.12, 0.12, 0.3, 16);
    const whistleMat = new THREE.MeshStandardMaterial({
        color: 0xffd700,
        roughness: 0.3,
        metalness: 0.8,
        emissive: 0x332200,
        emissiveIntensity: 0.2
    });
    const whistle = new THREE.Mesh(whistleGeo, whistleMat);
    whistle.position.y = arrowLength / 2 - 0.8;
    whistle.castShadow = true;
    arrowGroup.add(whistle);

    for (let i = 0; i < 3; i++) {
        const holeAngle = (i / 3) * Math.PI * 2;
        const holeGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.25, 8);
        const holeMat = new THREE.MeshStandardMaterial({
            color: 0x1a1a1a,
            roughness: 0.9
        });
        const hole = new THREE.Mesh(holeGeo, holeMat);
        hole.position.set(
            Math.cos(holeAngle) * 0.09,
            arrowLength / 2 - 0.8,
            Math.sin(holeAngle) * 0.09
        );
        hole.rotation.z = Math.PI / 2;
        hole.rotation.y = holeAngle;
        arrowGroup.add(hole);
    }

    const fletchingCount = 3;
    const fletchLength = 0.6;
    const fletchHeight = 0.15;

    for (let i = 0; i < fletchingCount; i++) {
        const angle = (i / fletchingCount) * Math.PI * 2;
        const fletchShape = new THREE.Shape();
        fletchShape.moveTo(0, 0);
        fletchShape.quadraticCurveTo(fletchLength / 2, fletchHeight * 0.8, fletchLength, 0);
        fletchShape.lineTo(fletchLength * 0.7, -fletchHeight * 0.3);
        fletchShape.lineTo(0, 0);

        const fletchGeo = new THREE.ExtrudeGeometry(fletchShape, {
            depth: 0.01,
            bevelEnabled: false
        });

        const fletchMat = new THREE.MeshStandardMaterial({
            color: 0x2a3a5c,
            side: THREE.DoubleSide,
            roughness: 0.7
        });

        const fletch = new THREE.Mesh(fletchGeo, fletchMat);
        fletch.position.set(
            Math.cos(angle) * shaftRadius,
            -arrowLength / 2 + 0.4,
            Math.sin(angle) * shaftRadius
        );
        fletch.rotation.y = angle;
        fletch.rotation.x = -Math.PI / 2;
        fletch.castShadow = true;
        arrowGroup.add(fletch);
    }

    arrowGroup.rotation.z = Math.PI / 2;
    arrowGroup.rotation.y = -0.3;
    arrowGroup.position.x = 0;
    scene.add(arrowGroup);
}

function createStreamlines() {
    const lineCount = 15;
    const pointsPerLine = 60;

    for (let i = 0; i < lineCount; i++) {
        const points = [];
        const yStart = -3 + (6 * i / (lineCount - 1));

        let x = -8, y = yStart;
        for (let j = 0; j < pointsPerLine; j++) {
            const speedFactor = 1.0 - 0.4 * Math.exp(-(y * y / 4));
            const vx = 1.0 * speedFactor;
            const vy = 0.05 * Math.sin(x * 0.3) + 0.02 * y;

            x += vx * 0.25;
            y += vy * 0.25;

            if (x > 8) break;
            points.push(new THREE.Vector3(x, y, 0));
        }

        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        const lineMat = new THREE.LineBasicMaterial({
            color: 0x66aaff,
            transparent: true,
            opacity: 0.6
        });
        const line = new THREE.Line(lineGeo, lineMat);
        line.visible = false;
        streamlines.push(line);
        scene.add(line);
    }
}

function createSoundField() {
    const size = 10;
    const segments = 50;
    const geometry = new THREE.PlaneGeometry(size, size, segments, segments);

    const material = new THREE.MeshBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.3,
        side: THREE.DoubleSide
    });

    soundFieldMesh = new THREE.Mesh(geometry, material);
    soundFieldMesh.rotation.x = -Math.PI / 2;
    soundFieldMesh.position.y = -1.9;
    soundFieldMesh.visible = false;
    scene.add(soundFieldMesh);

    updateSoundField(85);
}

function updateSoundField(spl) {
    if (!soundFieldMesh) return;

    const geometry = soundFieldMesh.geometry;
    const positions = geometry.attributes.position;
    const colors = [];

    const centerX = 0, centerZ = 0;
    const maxDist = 5;

    for (let i = 0; i < positions.count; i++) {
        const x = positions.getX(i);
        const z = positions.getZ(i);
        const dist = Math.sqrt(x * x + z * z);

        const normalizedDist = Math.min(dist / maxDist, 1);
        const localSpl = spl - 20 * Math.log10(Math.max(dist, 0.1)) + Math.random() * 2;

        const t = Math.max(0, Math.min(1, (localSpl - 40) / 60));

        const color = new THREE.Color();
        if (t < 0.25) {
            color.setRGB(0, 0.1, 0.3 + t);
        } else if (t < 0.5) {
            const tt = (t - 0.25) / 0.25;
            color.setRGB(0, 0.2 + tt * 0.6, 0.6 - tt * 0.3);
        } else if (t < 0.75) {
            const tt = (t - 0.5) / 0.25;
            color.setRGB(tt, 0.8 - tt * 0.3, 0.3 - tt * 0.2);
        } else {
            const tt = (t - 0.75) / 0.25;
            color.setRGB(1, 0.5 - tt * 0.4, 0.1 - tt * 0.1);
        }

        colors.push(color.r, color.g, color.b);
    }

    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geometry.attributes.color.needsUpdate = true;
}

function updateStreamlines(velocity) {
    streamlines.forEach((line, i) => {
        const positions = line.geometry.attributes.position;
        const yStart = -3 + (6 * i / (streamlines.length - 1));

        let x = -8, y = yStart;
        const factor = velocity / 65;

        for (let j = 0; j < positions.count; j++) {
            const speedFactor = 1.0 - 0.4 * Math.exp(-(y * y / 4));
            const vx = factor * speedFactor;
            const vy = 0.05 * Math.sin(x * 0.3) + 0.02 * y;

            x += vx * 0.25;
            y += vy * 0.25;

            if (x > 8) {
                positions.setX(j, null);
                break;
            }
            positions.setX(j, x);
            positions.setY(j, y);
        }
        positions.needsUpdate = true;
    });
}

function animate() {
    animationId = requestAnimationFrame(animate);

    if (arrowGroup) {
        arrowGroup.rotation.x += currentData.rotation_speed * 0.001;
        arrowGroup.position.y = Math.sin(Date.now() * 0.001) * 0.2;
    }

    controls.update();
    renderer.render(scene, camera);
}

function onWindowResize() {
    const container = document.getElementById('three-canvas').parentElement;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}

function setView(view) {
    currentView = view;
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });

    streamlines.forEach(line => {
        line.visible = (view === 'flow' || view === '3d');
    });

    if (soundFieldMesh) {
        soundFieldMesh.visible = (view === 'acoustic' || view === '3d');
        soundFieldMesh.material.opacity = view === 'acoustic' ? 0.6 : 0.2;
    }

    if (arrowGroup) {
        arrowGroup.visible = (view === '3d' || view === 'flow' || view === 'acoustic');
    }
}

function setupUI() {
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => setView(btn.dataset.view));
    });

    document.querySelectorAll('.arrow-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.arrow-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentArrow = chip.dataset.arrow;
            fetchData();
        });
    });

    const velCtrl = document.getElementById('velocity-control');
    velCtrl.addEventListener('input', (e) => {
        const val = e.target.value;
        document.getElementById('vel-control-val').textContent = val + ' m/s';
        currentData.velocity = parseFloat(val);
        updateStreamlines(currentData.velocity);
        runSimulation();
    });

    const angleCtrl = document.getElementById('angle-control');
    angleCtrl.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById('angle-control-val').textContent = val.toFixed(2) + ' rad';
        currentData.pitch = val;
        runSimulation();
    });

    const rotCtrl = document.getElementById('rotation-control');
    rotCtrl.addEventListener('input', (e) => {
        const val = e.target.value;
        document.getElementById('rot-control-val').textContent = val + ' rad/s';
        currentData.rotation_speed = parseFloat(val);
        runSimulation();
    });
}

function runSimulation() {
    fetch(`${API_BASE}/aerodynamics/simulate?velocity=${currentData.velocity}&angle_of_attack=${currentData.pitch}&rotation_speed=${currentData.rotation_speed}`)
        .then(r => r.json())
        .then(data => {
            currentData.drag_force = data.drag_force;
            currentData.lift_force = data.lift_force;
            currentData.moment = data.moment;
            currentData.reynolds_number = data.reynolds_number;
            currentData.drag_coefficient = data.drag_coefficient;
            currentData.lift_coefficient = data.lift_coefficient;
            updateUI();
        })
        .catch(err => console.log('Aero sim error:', err));

    fetch(`${API_BASE}/acoustics/simulate?velocity=${currentData.velocity}&rotation_speed=${currentData.rotation_speed}&distance=1`)
        .then(r => r.json())
        .then(data => {
            currentData.whistle_frequency = data.whistle_frequency;
            currentData.sound_pressure_level = data.sound_pressure_level;
            currentData.propagation_distance = data.propagation_distance;
            currentData.strouhal_number = data.strouhal_number;
            updateSoundField(currentData.sound_pressure_level);
            drawSoundFieldCanvas();
            updateUI();
        })
        .catch(err => console.log('Acoustics sim error:', err));
}

function fetchData() {
    fetch(`${API_BASE}/arrow/${currentArrow}/status`)
        .then(r => {
            if (!r.ok) throw new Error('No data');
            return r.json();
        })
        .then(data => {
            currentData.velocity = data.velocity;
            currentData.rotation_speed = data.rotation_speed;
            currentData.altitude = data.altitude;
            currentData.whistle_frequency = data.whistle_frequency;
            currentData.sound_pressure_level = data.sound_pressure_level;
            currentData.estimated_range = data.estimated_range;
            currentData.is_alert = data.is_alert;

            updateStreamlines(currentData.velocity);
            updateSoundField(currentData.sound_pressure_level);
            drawSoundFieldCanvas();
            updateUI();
            updateConnectionStatus(true);
        })
        .catch(err => {
            updateConnectionStatus(false);
            runSimulation();
        });

    fetchAlerts();
}

function fetchConfig() {
    fetch(`${API_BASE}/config`)
        .then(r => r.json())
        .then(data => {
            console.log('Config loaded:', data);
        })
        .catch(err => console.log('Config error:', err));
}

function fetchAlerts() {
    fetch(`${API_BASE}/alerts?arrow_id=${currentArrow}&limit=10`)
        .then(r => r.json())
        .then(data => {
            updateAlertsList(data.alerts || []);
        })
        .catch(err => {
            console.log('Alerts error:', err);
        });
}

function updateUI() {
    document.getElementById('velocity').textContent = currentData.velocity.toFixed(2);
    document.getElementById('rotation-speed').textContent = currentData.rotation_speed.toFixed(2);
    document.getElementById('altitude').textContent = currentData.altitude.toFixed(2);
    document.getElementById('pitch').textContent = currentData.pitch.toFixed(4);
    document.getElementById('range').textContent = currentData.estimated_range
        ? currentData.estimated_range.toFixed(1)
        : '—';

    document.getElementById('whistle-freq').textContent = currentData.whistle_frequency.toFixed(1);
    document.getElementById('spl').textContent = currentData.sound_pressure_level.toFixed(1);
    document.getElementById('prop-distance').textContent = currentData.propagation_distance.toFixed(1);
    document.getElementById('strouhal').textContent = currentData.strouhal_number.toFixed(3);
    document.getElementById('reynolds').textContent = Math.round(currentData.reynolds_number).toLocaleString();

    document.getElementById('drag-force').textContent = currentData.drag_force.toFixed(3);
    document.getElementById('lift-force').textContent = currentData.lift_force.toFixed(3);
    document.getElementById('drag-coef').textContent = currentData.drag_coefficient.toFixed(3);
    document.getElementById('lift-coef').textContent = currentData.lift_coefficient.toFixed(3);
    document.getElementById('moment').textContent = currentData.moment.toFixed(3);

    const splPercent = Math.min(100, Math.max(0, (currentData.sound_pressure_level - 40) / 80 * 100));
    document.getElementById('spl-bar').style.width = splPercent + '%';

    const rangeEl = document.getElementById('range');
    if (currentData.estimated_range < 150) {
        rangeEl.classList.add('alert');
    } else {
        rangeEl.classList.remove('alert');
    }
}

function updateAlertsList(alerts) {
    const container = document.getElementById('alerts-list');

    if (alerts.length === 0) {
        container.innerHTML = '<div style="color: #4a5568; font-size: 12px; text-align: center; padding: 20px 0;">暂无告警</div>';
        return;
    }

    container.innerHTML = alerts.map(alert => `
        <div class="alert-item ${alert.severity === 'critical' ? 'critical' : 'warning'}">
            <div class="alert-type">${alertTypeLabel(alert.alert_type)}</div>
            <div class="alert-msg">${alert.message}</div>
            <div class="alert-time">${formatTime(alert.timestamp)}</div>
        </div>
    `).join('');
}

function alertTypeLabel(type) {
    const labels = {
        'frequency_low': '哨音频率偏低',
        'frequency_high': '哨音频率偏高',
        'range_insufficient': '射程不足',
        'spl_low': '声压级偏低'
    };
    return labels[type] || type;
}

function formatTime(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString('zh-CN');
    } catch {
        return isoString;
    }
}

function updateConnectionStatus(online) {
    const statusEl = document.getElementById('connection-status');
    if (online) {
        statusEl.textContent = '● 系统在线';
        statusEl.className = 'status-badge online';
    } else {
        statusEl.textContent = '● 离线模式';
        statusEl.className = 'status-badge';
    }

    const countEl = document.getElementById('sensor-count');
    countEl.textContent = '传感器: 3';
}

function drawSoundFieldCanvas() {
    const canvas = document.getElementById('sound-field-canvas');
    const ctx = canvas.getContext('2d');
    const w = canvas.width = 240;
    const h = canvas.height = 180;

    ctx.fillStyle = '#0a0e17';
    ctx.fillRect(0, 0, w, h);

    const centerX = w / 2;
    const centerY = h / 2;
    const maxR = Math.min(w, h) * 0.45;

    const maxSpl = currentData.sound_pressure_level;

    for (let r = maxR; r > 0; r -= 1) {
        const distRatio = r / maxR;
        const dist = distRatio * 10;
        const spl = maxSpl - 20 * Math.log10(Math.max(dist, 0.1));
        const t = Math.max(0, Math.min(1, (spl - 40) / 60));

        let rC, gC, bC;
        if (t < 0.25) {
            rC = 0; gC = 25; bC = 80 + t * 680;
        } else if (t < 0.5) {
            const tt = (t - 0.25) / 0.25;
            rC = 0; gC = 50 + tt * 150; bC = 150 - tt * 75;
        } else if (t < 0.75) {
            const tt = (t - 0.5) / 0.25;
            rC = tt * 255; gC = 200 - tt * 75; bC = 75 - tt * 50;
        } else {
            const tt = (t - 0.75) / 0.25;
            rC = 255; gC = 125 - tt * 100; bC = 25 - tt * 25;
        }

        ctx.beginPath();
        ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${Math.round(rC)}, ${Math.round(gC)}, ${Math.round(bC)}, 0.6)`;
        ctx.fill();
    }

    ctx.fillStyle = '#ffd700';
    ctx.beginPath();
    ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#ffd700';
    ctx.font = '10px Consolas, monospace';
    ctx.fillText(`${maxSpl.toFixed(0)} dB`, centerX + 10, centerY - 10);

    ctx.strokeStyle = '#2a3a5c';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.arc(centerX, centerY, maxR * 0.5, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
}

window.addEventListener('load', init);
