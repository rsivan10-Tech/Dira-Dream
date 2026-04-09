# Three.js Architectural Visualization Patterns

## Wall Extrusion from 2D Plan

Convert 2D wall segments into 3D wall meshes:

```typescript
import * as THREE from 'three';

interface WallParams {
  start: { x: number; y: number };  // cm
  end: { x: number; y: number };    // cm
  thickness: number;                  // cm
  height: number;                     // cm, default 260
  wallType: string;
}

function createWallMesh(wall: WallParams): THREE.Mesh {
  // Convert cm to meters for Three.js
  const s = { x: wall.start.x / 100, z: wall.start.y / 100 };
  const e = { x: wall.end.x / 100, z: wall.end.y / 100 };
  const h = wall.height / 100;
  const t = wall.thickness / 100;

  // Calculate wall length and angle
  const dx = e.x - s.x;
  const dz = e.z - s.z;
  const length = Math.sqrt(dx * dx + dz * dz);
  const angle = Math.atan2(dz, dx);

  // Create box geometry (length x height x thickness)
  const geometry = new THREE.BoxGeometry(length, h, t);

  // Position at midpoint, half-height up
  const mesh = new THREE.Mesh(geometry, getWallMaterial(wall.wallType));
  mesh.position.set(
    (s.x + e.x) / 2,
    h / 2,         // Y is UP in Three.js
    (s.z + e.z) / 2
  );
  mesh.rotation.y = -angle;

  mesh.userData = { wallType: wall.wallType, thickness: wall.thickness };
  return mesh;
}
```

## Coordinate Mapping (2D → 3D)

```
2D Canvas (Konva):     3D Scene (Three.js):
  X → right              X → right (same)
  Y → down               Y → UP
                          Z → forward (was Y in 2D)

Conversion: cm → meters
  3D.x = 2D.x / 100
  3D.y = height / 100     (0 = floor, 2.6 = ceiling)
  3D.z = 2D.y / 100
```

## CSG for Door/Window Openings

Use CSG (Constructive Solid Geometry) to cut holes in walls:

```typescript
import { SUBTRACTION, Evaluator, Brush } from 'three-bvh-csg';

function createWallWithOpening(
  wall: WallParams,
  opening: { position: number; width: number; height: number; sillHeight: number }
): THREE.Mesh {
  // Create wall brush
  const wallGeom = new THREE.BoxGeometry(wallLength, wallHeight, wallThickness);
  const wallBrush = new Brush(wallGeom);
  wallBrush.position.copy(wallCenter);
  wallBrush.updateMatrixWorld();

  // Create opening brush (the hole to cut)
  const openingGeom = new THREE.BoxGeometry(
    opening.width / 100,
    opening.height / 100,
    wallThickness * 1.1  // Slightly thicker to ensure clean cut
  );
  const openingBrush = new Brush(openingGeom);
  openingBrush.position.set(
    openingCenterX,
    opening.sillHeight / 100 + opening.height / 200,  // Centered vertically
    wallCenterZ
  );
  openingBrush.updateMatrixWorld();

  // Subtract opening from wall
  const evaluator = new Evaluator();
  const result = evaluator.evaluate(wallBrush, openingBrush, SUBTRACTION);

  return new THREE.Mesh(result.geometry, getWallMaterial(wall.wallType));
}
```

### Opening Dimensions
- **Door**: width 70-100cm, height 210cm, sill 0cm
- **Window**: width 100-200cm, height 120cm, sill 90cm
- **Mamad blast window**: width 60cm, height 60cm, sill 120cm
- **French door**: width 160-200cm, height 220cm, sill 0cm
- **Sliding door**: width 200-300cm, height 220cm, sill 0cm

## Floor and Ceiling

```typescript
function createFloor(envelope: number[][]): THREE.Mesh {
  // envelope: 2D polygon vertices in cm
  const shape = new THREE.Shape();
  shape.moveTo(envelope[0][0] / 100, envelope[0][1] / 100);
  for (let i = 1; i < envelope.length; i++) {
    shape.lineTo(envelope[i][0] / 100, envelope[i][1] / 100);
  }
  shape.closePath();

  const geometry = new THREE.ShapeGeometry(shape);
  geometry.rotateX(-Math.PI / 2);  // Lay flat (XZ plane)

  const material = new THREE.MeshStandardMaterial({
    color: 0xf5f5f0,
    roughness: 0.8,
  });

  return new THREE.Mesh(geometry, material);
}

function createCeiling(envelope: number[][], height: number = 260): THREE.Mesh {
  const floor = createFloor(envelope);
  floor.position.y = height / 100;  // Move to ceiling height
  floor.material = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.9,
    side: THREE.BackSide,
  });
  return floor;
}
```

## Glass Material (Windows)

```typescript
const glassMaterial = new THREE.MeshPhysicalMaterial({
  color: 0x88ccff,
  metalness: 0,
  roughness: 0.05,
  transmission: 0.9,    // See-through
  thickness: 0.01,      // Thin glass
  ior: 1.5,             // Index of refraction
  transparent: true,
  opacity: 0.3,
  side: THREE.DoubleSide,
});

function createWindowGlass(opening: Opening): THREE.Mesh {
  const geometry = new THREE.PlaneGeometry(
    opening.width / 100,
    opening.height / 100
  );
  const mesh = new THREE.Mesh(geometry, glassMaterial);
  // Position in the wall opening
  mesh.position.set(openingX, openingY, wallZ);
  mesh.rotation.y = wallAngle;
  return mesh;
}
```

## First-Person Camera Controller

```typescript
import { useFrame, useThree } from '@react-three/fiber';

const CAMERA_HEIGHT = 1.65;  // meters (eye height)
const MOVE_SPEED = 3.0;      // meters/sec
const LOOK_SPEED = 0.002;    // radians/pixel
const COLLISION_RADIUS = 0.3; // meters

function FirstPersonController({ walls }: { walls: THREE.Mesh[] }) {
  const { camera } = useThree();
  const velocity = useRef(new THREE.Vector3());
  const euler = useRef(new THREE.Euler(0, 0, 0, 'YXZ'));

  useEffect(() => {
    camera.position.set(startX, CAMERA_HEIGHT, startZ);

    const onKeyDown = (e: KeyboardEvent) => {
      switch (e.code) {
        case 'KeyW': velocity.current.z = -MOVE_SPEED; break;
        case 'KeyS': velocity.current.z = MOVE_SPEED; break;
        case 'KeyA': velocity.current.x = -MOVE_SPEED; break;
        case 'KeyD': velocity.current.x = MOVE_SPEED; break;
      }
    };

    const onMouseMove = (e: MouseEvent) => {
      if (document.pointerLockElement) {
        euler.current.y -= e.movementX * LOOK_SPEED;
        euler.current.x -= e.movementY * LOOK_SPEED;
        euler.current.x = Math.max(-Math.PI/3, Math.min(Math.PI/3, euler.current.x));
        camera.quaternion.setFromEuler(euler.current);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('mousemove', onMouseMove);
    return () => { /* cleanup */ };
  }, []);

  useFrame((_, delta) => {
    // Move in camera's forward direction
    const direction = new THREE.Vector3();
    direction.copy(velocity.current);
    direction.applyQuaternion(camera.quaternion);
    direction.y = 0;  // Stay on ground

    const newPos = camera.position.clone().add(direction.multiplyScalar(delta));

    // Wall collision check
    if (!checkCollision(newPos, walls, COLLISION_RADIUS)) {
      camera.position.copy(newPos);
      camera.position.y = CAMERA_HEIGHT;  // Lock height
    }
  });

  return null;
}
```

## Wall Collision Detection

```typescript
function checkCollision(
  position: THREE.Vector3,
  walls: THREE.Mesh[],
  radius: number
): boolean {
  const raycaster = new THREE.Raycaster();
  const directions = [
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(-1, 0, 0),
    new THREE.Vector3(0, 0, 1),
    new THREE.Vector3(0, 0, -1),
    // Diagonal checks
    new THREE.Vector3(0.707, 0, 0.707),
    new THREE.Vector3(-0.707, 0, 0.707),
    new THREE.Vector3(0.707, 0, -0.707),
    new THREE.Vector3(-0.707, 0, -0.707),
  ];

  for (const dir of directions) {
    raycaster.set(position, dir);
    raycaster.far = radius;
    const hits = raycaster.intersectObjects(walls);
    if (hits.length > 0) return true;
  }
  return false;
}
```

## Performance Optimization

### Instancing for Repeated Elements
```typescript
// For walls with same material, use instanced mesh
const instancedWalls = new THREE.InstancedMesh(
  wallGeometry,
  wallMaterial,
  wallCount
);

walls.forEach((wall, i) => {
  const matrix = new THREE.Matrix4();
  matrix.compose(wall.position, wall.quaternion, wall.scale);
  instancedWalls.setMatrixAt(i, matrix);
});
instancedWalls.instanceMatrix.needsUpdate = true;
```

### Level of Detail
- Close: Full geometry with textures
- Medium: Simplified geometry, basic materials
- Far: Box approximations

### Frustum Culling
Three.js does this automatically for meshes. Ensure:
- Bounding spheres/boxes are computed: `mesh.geometry.computeBoundingSphere()`
- `mesh.frustumCulled = true` (default)

### Lighting
```typescript
// Ambient for base illumination
const ambient = new THREE.AmbientLight(0xffffff, 0.5);

// Directional for sun
const sun = new THREE.DirectionalLight(0xffffff, 0.8);
sun.position.set(10, 20, 10);
sun.castShadow = true;

// Point lights per room for interior feel
rooms.forEach(room => {
  const light = new THREE.PointLight(0xfff5e6, 0.6, 8);
  light.position.set(room.center.x, 2.4, room.center.z);
  scene.add(light);
});
```

## React Three Fiber Integration

```tsx
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Environment } from '@react-three/drei';

const FloorplanScene = ({ apartment }) => (
  <Canvas
    camera={{ position: [0, 10, 0], fov: 60 }}
    shadows
    dpr={[1, 2]}
    performance={{ min: 0.5 }}
  >
    <ambientLight intensity={0.5} />
    <directionalLight position={[10, 20, 10]} castShadow />

    <Floor envelope={apartment.envelope} />
    <Ceiling envelope={apartment.envelope} height={260} />

    {apartment.walls.map(wall => (
      <Wall key={wall.id} wall={wall} />
    ))}

    {apartment.openings.map(opening => (
      <Opening key={opening.id} opening={opening} />
    ))}

    <OrbitControls
      enableDamping
      dampingFactor={0.05}
      minDistance={1}
      maxDistance={30}
    />
  </Canvas>
);
```

## Target Performance
- **60fps** on mid-range mobile devices
- **Max triangles**: ~100K for apartment scene
- **Texture budget**: 64MB total
- **Draw calls**: <50 (use instancing and merging)
