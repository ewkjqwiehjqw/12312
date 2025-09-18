// Global variables
let scene, camera, renderer, controls
let teethModel
let selectedTeeth = []
let currentMaterial = "gold"
let showOnlySelected = false // Toggle state for "show only selected teeth"
let currentStep = 1 // Track current step in the process
let selectedCrypto = "BTC"  // Default to Bitcoin
let materialPrices = {}  // Will be populated from API

// Material definitions for 3D models with enhanced properties
const materials3D = {
  gold: {
    color: 0x996600,           // MUCH darker, deeper gold - almost bronze
    metalness: 1.0,
    roughness: 0.01,           // Maximum shine
    emissive: 0x331100,        // Add warm glow back
    envMapIntensity: 6.0,      // Even more environmental reflections
    clearcoat: 1.0,            // Full clearcoat for extra shine
    clearcoatRoughness: 0.0    // Perfect clearcoat finish
  },
  silver: { 
    color: 0xF5F5F5, // Bright chrome silver
    metalness: 1.0, 
    roughness: 0.01, // Mirror-like chrome finish
    emissive: 0x000000, // No emission for pure chrome look
    envMapIntensity: 4.0, // Maximum reflectivity for chrome
    clearcoat: 1.0, // Full chrome coating
    clearcoatRoughness: 0.0
  },
  diamond: {
    color: 0xFFFFFF, // Pure white
    metalness: 0.8, // More metallic for bling effect
    roughness: 0.0, // Perfect smoothness
    emissive: 0x002266, // Subtle blue sparkle
    clearcoat: 1.0, // Maximum clarity
    clearcoatRoughness: 0.0,
    ior: 1.5, // Reduced refraction for less weirdness
    transmission: 0.0, // NO transparency - solid iced grillz
    opacity: 1.0, // Solid appearance
    envMapIntensity: 6.0, // Maximum sparkle
    sheen: 1.0, // Extra sparkle effect
    sheenColor: 0xCCDDFF // Lighter blue sheen for ice effect
  },
}

// Track loading state
let resourcesLoaded = {
  model: false,
  textures: false,
  fonts: false
};

function checkAllResourcesLoaded() {
  if (Object.values(resourcesLoaded).every(loaded => loaded)) {
    const loadingScreen = document.getElementById("loadingScreen");
    if (loadingScreen) {
      loadingScreen.style.opacity = "0";
      setTimeout(() => {
        loadingScreen.style.display = "none";
      }, 500);
    }
    window.interactionsEnabled = true;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  // Show loading screen
  const loadingScreen = document.getElementById("loadingScreen");
  if (loadingScreen) {
    loadingScreen.style.display = "flex";
    loadingScreen.style.opacity = "1";
  }

  // Fetch prices from API
  try {
    const pricesRes = await utils.apiClient.get('/api/prices');
    materialPrices = pricesRes.materials;
    
    // Update material options with fetched prices
    document.querySelectorAll('.material-option').forEach(option => {
      const material = option.dataset.material;
      if (materialPrices[material]) {
        const priceTag = option.querySelector('.price-tag');
        const materialName = option.querySelector('.material-name');
        if (priceTag) priceTag.textContent = `$${materialPrices[material].price}`;
        if (materialName) materialName.textContent = materialPrices[material].name;
      }
    });
  } catch (error) {
    console.error('Failed to fetch prices:', error);
    utils.showToast('Failed to load current prices', 'error');
  }

  // Check when fonts are loaded
  document.fonts.ready.then(() => {
    resourcesLoaded.fonts = true;
    checkAllResourcesLoaded();
  });

  init3DScene();
  setupEventListeners();
  updatePrice();
  updateSummary();
  animate();
  
  // Initialize order page after scene is ready
  if (typeof initializeOrderPage === 'function') {
    initializeOrderPage();
  }
})

function init3DScene() {
  const canvas = document.getElementById("threejs-canvas")
  const container = canvas.parentElement

  scene = new THREE.Scene()
  scene.background = null
  window.scene = scene  // Make scene globally available

  camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 1000)
  camera.position.set(0, 1, 6) // Better camera position to view teeth from front

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setSize(container.clientWidth, container.clientHeight)
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.5
  renderer.outputColorSpace = THREE.SRGBColorSpace

  controls = new THREE.OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05
  controls.minDistance = 3
  controls.maxDistance = 12
  controls.target.set(0, 0, 0)

  setupLighting()
  loadModels() // Load the realistic teeth model

  window.addEventListener("resize", onWindowResize)
  onWindowResize()
}

function setupLighting() {
  scene.add(new THREE.AmbientLight(0xffffff, 0.4))

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.7)
  keyLight.position.set(5, 5, 5)
  keyLight.castShadow = true
  keyLight.shadow.mapSize.width = 2048
  keyLight.shadow.mapSize.height = 2048
  scene.add(keyLight)

  const fillLight = new THREE.DirectionalLight(0xffffff, 0.5)
  fillLight.position.set(-5, 2, 3)
  scene.add(fillLight)

  const rimLight = new THREE.DirectionalLight(0xffffff, 0.5)
  rimLight.position.set(0, 5, -5)
  scene.add(rimLight)

  // Using a simple environment map for reflections
  const pmremGenerator = new THREE.PMREMGenerator(renderer)
  pmremGenerator.compileEquirectangularShader()
  new THREE.TextureLoader().load(
    "https://sjc.microlink.io/DALgH5-uN2OXcUZH93wwM17XGGKo0Td8oHHDHnHsAlTSoXRGhboRsubVu9q-8f1tWKwm2Y7kI9vvNDRgjFuLDw.jpeg",
    (texture) => {
      const envMap = pmremGenerator.fromEquirectangular(texture).texture
      scene.environment = envMap
      texture.dispose()
      pmremGenerator.dispose()
      
      // Mark textures as loaded
      resourcesLoaded.textures = true
      checkAllResourcesLoaded()
    },
  )
}

function loadModels() {
  const loader = new THREE.GLTFLoader() // Use GLTFLoader from global THREE
  const loadingScreen = document.getElementById("loadingScreen")

  loader.load(
    "/static/models/new.glb", // serve via FastAPI static (GLB)
    (gltf) => {
      // gltf.scene contains the loaded scene or model
      teethModel = gltf.scene // Assign the loaded scene to our teethModel variable

      // Create materials for teeth and gums - nice white platinum color
      const toothMaterial = new THREE.MeshStandardMaterial({
        color: 0xf5f5f5, // Nice white platinum color
        roughness: 0.3,
        metalness: 0.2,
      })
      const gumMaterial = new THREE.MeshStandardMaterial({
        color: 0x8c3b3b, // A fleshy pink/red for gums
        roughness: 0.8,
        metalness: 0.0,
      })

      // Store individual teeth for direct selection
      const individualTeeth = []
      
      teethModel.traverse((child) => {
        if (child.isMesh) {
          child.castShadow = true
          child.receiveShadow = true
          
          // Store original material for restoration
          child.userData.originalMaterial = toothMaterial.clone()
          child.material = child.userData.originalMaterial
          
          // Only make the 16 target teeth selectable
          const targetNames = [
            'Tooth003', 'Tooth004', 'Tooth005', 'Tooth006', 'Tooth007', 'Tooth008', 'Tooth009', 'Tooth010',
            'Tooth017', 'Tooth018', 'Tooth019', 'Tooth020', 'Tooth021', 'Tooth022', 'Tooth023', 'Tooth024'
          ]
          const isSelectableTooth = child.name && targetNames.includes(child.name)
          
          if (isSelectableTooth) {
            // Assign unique sequential tooth index (no duplicates)
            const toothIndex = individualTeeth.length + 1
            
            child.userData.toothIndex = toothIndex
            child.userData.isSelectable = true
            child.userData.originalName = child.name
            individualTeeth.push(child)
          }
          
          // Compute bounding box volume to aid later filtering
          if (child.geometry) {
            child.geometry.computeBoundingBox()
            const bb = child.geometry.boundingBox
            const vol = (bb.max.x - bb.min.x) * (bb.max.y - bb.min.y) * (bb.max.z - bb.min.z)
            child.userData.volume = vol
          }
        }
      })
      
      // Create mapping between UI buttons and detected teeth
      window.detectedTeeth = individualTeeth.map(tooth => ({
        index: tooth.userData.toothIndex,
        name: tooth.userData.originalName,
        mesh: tooth
      }))
      
      // Create proper dental mapping for UI buttons
      window.dentalMapping = createDentalMapping(individualTeeth)

      // Scale and position the model properly
      const bbox = new THREE.Box3().setFromObject(teethModel)
      const center = bbox.getCenter(new THREE.Vector3())
      const size = bbox.getSize(new THREE.Vector3())

      const maxDim = Math.max(size.x, size.y, size.z)
      const scale = 4.0 / maxDim // Scale the model to a good size

      teethModel.scale.set(scale, scale, scale)
      
      // Fix orientation - flip to show teeth properly (top row on top)
      teethModel.rotation.set(0, 0, 0) // Reset rotation first
      teethModel.rotation.x = 0 // No X rotation (don't flip upside down)
      teethModel.rotation.y = 0 // Face forward
      teethModel.rotation.z = 0 // No Z rotation
      
      // Center the model properly
      const centeredBbox = new THREE.Box3().setFromObject(teethModel)
      const centeredCenter = centeredBbox.getCenter(new THREE.Vector3())
      teethModel.position.set(-centeredCenter.x, -centeredCenter.y, -centeredCenter.z)
      
      // Final positioning adjustments
      teethModel.position.y += 0.2 // Lift it up slightly for better view

      scene.add(teethModel)

      // Now that teeth are loaded, setup the teeth coloring system
      setupTeethColoringSystem()

      // Create teeth meshes for the order page
      if (typeof createTeethMeshes === 'function') {
        createTeethMeshes();
      }

      // Mark model as loaded
      resourcesLoaded.model = true
      checkAllResourcesLoaded()
    },
    (xhr) => {
      // Update loading progress
      if (xhr.lengthComputable) {
        const percent = Math.round((xhr.loaded / xhr.total) * 100)
        const loadingScreen = document.getElementById("loadingScreen")
        if (loadingScreen) {
          loadingScreen.querySelector("p").textContent = `Loading 3D model... ${percent}%`
        }
      }
    },
    (error) => {
      if (loadingScreen) {
        loadingScreen.querySelector("h3").textContent = "Error loading 3D model"
        loadingScreen.querySelector("p").textContent = "Please refresh the page or try using a fallback model."
      }
      // Create a fallback scene with basic geometry if model fails to load
      createFallbackScene()
    },
  )
}

function createFallbackScene() {
  // Create a fallback scene with basic tooth geometry if OBJ fails to load
  const fallbackGroup = new THREE.Group()
  
  // Create 12 basic tooth shapes
  for (let i = 0; i < 12; i++) {
    const toothGeometry = new THREE.BoxGeometry(0.3, 0.5, 0.2)
    const toothMaterial = new THREE.MeshStandardMaterial({
      color: 0xf5f5f5, // Nice white platinum color
      roughness: 0.3,
      metalness: 0.2,
    })
    const tooth = new THREE.Mesh(toothGeometry, toothMaterial)
    
    // Position teeth in an arc
    const angle = (i / 12) * Math.PI * 2
    const radius = 1.5
    tooth.position.x = Math.cos(angle) * radius
    tooth.position.z = Math.sin(angle) * radius
    tooth.position.y = 0
    
    // Rotate to face center
    tooth.lookAt(0, 0, 0)
    
    fallbackGroup.add(tooth)
  }
  
  teethModel = fallbackGroup
  scene.add(teethModel)
  setupTeethColoringSystem()
  
  // Mark resources as loaded in fallback mode
  resourcesLoaded.model = true
  resourcesLoaded.textures = true
  checkAllResourcesLoaded()
}

function setupTeethColoringSystem() {
  if (!teethModel) return

  // Setup direct tooth selection system using the loaded meshes
  setupDirectToothSelection()
}

function createDentalMapping(individualTeeth) {
  // Create mapping between UI buttons and actual dental positions
  // 8 teeth per row, numbered from center outward
  const mapping = {}
  
  // Complete mapping using actual GLB names (no dots)
  const toothMappings = {
    // Top row
    'T1': 'Tooth003',
    'T2': 'Tooth004', 
    'T3': 'Tooth005',
    'T4': 'Tooth006',
    'T5': 'Tooth007',
    'T6': 'Tooth008',
    'T7': 'Tooth009',
    'T8': 'Tooth010',
    // Bottom row
    'B1': 'Tooth017',
    'B2': 'Tooth018',
    'B3': 'Tooth019',
    'B4': 'Tooth020',
    'B5': 'Tooth021',
    'B6': 'Tooth022',
    'B7': 'Tooth023',
    'B8': 'Tooth024'
  }
  
  // Map each UI button to its corresponding tooth
  Object.entries(toothMappings).forEach(([uiPos, toothName]) => {
    const tooth = individualTeeth.find(t => t.userData.originalName === toothName)
    if (tooth) {
      mapping[uiPos] = tooth.userData.toothIndex
    }
  })
  
  return mapping
}

function setupDirectToothSelection() {
  // Setup click detection for individual teeth
  setupToothClickDetection()
  
  // Find available teeth for selection
  const availableTeeth = []
  if (teethModel) {
    teethModel.traverse((child) => {
      if (child.isMesh && child.userData.isSelectable) {
        availableTeeth.push(child.userData.toothIndex)
      }
    })
  }
  
  // Auto-select front teeth for demo 
  setTimeout(() => {
    // Select prominent front teeth for demo using dental mapping
    selectedTeeth = []
    
    if (window.dentalMapping) {
      // Select some front teeth for demo
      const demoPositions = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8'] // Center front teeth
      
      demoPositions.forEach(position => {
        if (window.dentalMapping[position]) {
          selectedTeeth.push(window.dentalMapping[position])
        }
      })
    }
    
    // Fallback to first available teeth if no mapping
    if (selectedTeeth.length === 0) {
      const numToSelect = Math.min(4, availableTeeth.length)
      selectedTeeth = availableTeeth.slice(0, numToSelect)
    }
    
    updateTeethUI()
    updateDirectToothMaterials()
    updatePrice()
    updateSummary()
  }, 200)
}

function setupToothClickDetection() {
  const canvas = document.getElementById("threejs-canvas")
  const raycaster = new THREE.Raycaster()
  const mouse = new THREE.Vector2()
  
  function onToothClick(event) {
    if (!teethModel || !window.interactionsEnabled) return
    
    // Calculate mouse position in normalized device coordinates
    const rect = canvas.getBoundingClientRect()
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
    
    // Cast ray from camera
    raycaster.setFromCamera(mouse, camera)
    
    // Find intersections with selectable teeth
    const selectableTeeth = []
    teethModel.traverse((child) => {
      if (child.isMesh && child.userData.isSelectable) {
        selectableTeeth.push(child)
      }
    })
    
    const intersects = raycaster.intersectObjects(selectableTeeth)
    
    if (intersects.length > 0) {
      const clickedTooth = intersects[0].object
      const toothIndex = clickedTooth.userData.toothIndex
      
      // Toggle selection
      toggleToothSelection(toothIndex)
      updateTeethUI()
      updateDirectToothMaterials()
      updatePrice()
      updateSummary()
    }
  }
  
  canvas.addEventListener('click', onToothClick)
}

function createGrillzMaterial(materialType) {
  const matProps = materials3D[materialType]
  if (!matProps) {
    return new THREE.MeshStandardMaterial({ color: 0xff00ff })
  }

  let material
  if (materialType === "diamond") {
    // Use MeshPhysicalMaterial for diamond - SOLID iced out grillz
    material = new THREE.MeshPhysicalMaterial({
      color: matProps.color,
      metalness: matProps.metalness,
      roughness: matProps.roughness,
      emissive: matProps.emissive || 0x000000,
      clearcoat: matProps.clearcoat || 1.0,
      clearcoatRoughness: matProps.clearcoatRoughness || 0.0,
      ior: matProps.ior || 1.5,
      transmission: 0.0, // Force to 0 - no transparency
      transparent: false, // Explicitly solid
      opacity: 1.0, // Fully opaque
      envMapIntensity: matProps.envMapIntensity || 6.0,
      sheen: matProps.sheen || 1.0,
      sheenColor: new THREE.Color(matProps.sheenColor || 0xCCDDFF)
    })
  } else {
    // Use MeshPhysicalMaterial for gold and silver to support clearcoat
    material = new THREE.MeshPhysicalMaterial({
      color: matProps.color,
      metalness: matProps.metalness,
      roughness: matProps.roughness,
      emissive: matProps.emissive || 0x000000,
      envMapIntensity: matProps.envMapIntensity || 2.0,
      clearcoat: matProps.clearcoat || 0.0,
      clearcoatRoughness: matProps.clearcoatRoughness || 0.0,
    })
  }
  
  // Apply environment map if available
  if (window.scene && window.scene.environment) {
    material.envMap = window.scene.environment
  }
  
  return material
}

function setupEventListeners() {
  // --- Event listeners remain largely the same as before ---
  document.querySelectorAll(".material-option").forEach((option) => {
    option.addEventListener("click", function () {
      document.querySelectorAll(".material-option").forEach((opt) => opt.classList.remove("active"))
      this.classList.add("active")
      currentMaterial = this.dataset.material
      updateGrillzMaterial()
      updatePrice()
      updateSummary()
    })
  })

  document.querySelectorAll(".tooth").forEach((tooth) => {
    tooth.addEventListener("click", function () {
      const buttonId = this.dataset.tooth
      const uiPosition = buttonId <= 8 ? `T${buttonId}` : `B${buttonId - 8}`
      
      // Use dental mapping to get the correct tooth index
      if (window.dentalMapping && window.dentalMapping[uiPosition]) {
        const actualToothIndex = window.dentalMapping[uiPosition]
        toggleToothSelection(actualToothIndex)
        updateTeethUI()
        updateDirectToothMaterials()
        updatePrice()
        updateSummary()
      }
    })
  })

  const clearSelectionBtn = document.getElementById("clearSelection")
  const resetViewBtn = document.getElementById("resetView")
  const fullscreenBtn = document.getElementById("fullscreen")
  const hideUnselectedBtn = document.getElementById("hideUnselected")
  const continueBtn = document.getElementById("continueBtn")
  const backBtn = document.getElementById("backBtn")

  if (clearSelectionBtn) clearSelectionBtn.addEventListener("click", clearTeethSelection)
  if (resetViewBtn) resetViewBtn.addEventListener("click", resetCameraView)
  if (fullscreenBtn) fullscreenBtn.addEventListener("click", toggleFullscreen)
  if (hideUnselectedBtn) hideUnselectedBtn.addEventListener("click", toggleUnneededParts)
  if (continueBtn) continueBtn.addEventListener("click", handleContinue)
  if (backBtn) backBtn.addEventListener("click", handleBack)

  // Crypto currency selection
  document.querySelectorAll('.crypto-option').forEach(option => {
    option.addEventListener('click', function() {
      document.querySelectorAll('.crypto-option').forEach(opt => opt.classList.remove('active'));
      this.classList.add('active');
      selectedCrypto = this.dataset.currency;
      updateFinalOverview();
    });
  });
}

function toggleToothSelection(toothIndex) {
  const index = selectedTeeth.indexOf(toothIndex)
  if (index > -1) {
    selectedTeeth.splice(index, 1)
  } else {
    selectedTeeth.push(toothIndex)
  }
  updateTeethVisibility()
}

function clearTeethSelection() {
  selectedTeeth = []
  updateTeethUI()
  updateDirectToothMaterials() // This will restore original materials for all teeth
  updatePrice()
  updateSummary()
}

function applyVisibilitySettings() {
  if (!teethModel) return
  
  let hiddenCount = 0
  let shownCount = 0
  
  teethModel.traverse((child) => {
    if (child.isMesh) {
      if (showOnlySelected) {
        // Hide everything except selected teeth
        if (child.userData.isSelectable && child.userData.toothIndex && selectedTeeth.includes(child.userData.toothIndex)) {
          // This is a selected tooth - keep it visible
          child.visible = true
          shownCount++
        } else {
          // Hide everything else (unselected teeth, jaws, etc.)
          child.visible = false
          hiddenCount++
        }
      } else {
        // Show everything
        child.visible = true
        shownCount++
      }
    }
  })
}

function toggleUnneededParts() {
  // Toggle the state
  showOnlySelected = !showOnlySelected
  
  const toggleBtn = document.getElementById("hideUnselected")
  if (toggleBtn) {
    // Update button appearance
    if (showOnlySelected) {
      toggleBtn.classList.add("active")
      toggleBtn.title = "Show all teeth"
      toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>'
    } else {
      toggleBtn.classList.remove("active")
      toggleBtn.title = "Show only selected teeth"
      toggleBtn.innerHTML = '<i class="fas fa-eye"></i>'
    }
  }
  
  // Apply the visibility changes
  applyVisibilitySettings()
}

function updateTeethUI() {
  document.querySelectorAll(".tooth").forEach((tooth) => {
    const buttonId = tooth.dataset.tooth
    const uiPosition = buttonId <= 8 ? `T${buttonId}` : `B${buttonId - 8}`
    
    // Check if this UI position corresponds to a selected tooth
    let isSelected = false
    if (window.dentalMapping && window.dentalMapping[uiPosition]) {
      const mappedToothIndex = window.dentalMapping[uiPosition]
      isSelected = selectedTeeth.includes(mappedToothIndex)
    }
    
    tooth.classList.toggle("selected", isSelected)
  })
}

function updateTeethVisibility() {
  // Update direct tooth materials based on selection
  updateDirectToothMaterials()
}

function updateDirectToothMaterials() {
  if (!teethModel) return
  
  let updatedCount = 0
  let totalSelectableTeeth = 0
  
  // Create a fresh white tooth material to ensure consistency - completely isolated
  const whiteToothMaterial = new THREE.MeshStandardMaterial({
    color: 0xf5f5f5, // Nice white platinum color
    roughness: 0.3,
    metalness: 0.2,
    emissive: 0x000000, // No emission
    envMapIntensity: 1.0, // Normal reflectivity
    transparent: false, // Explicitly not transparent
    opacity: 1.0, // Fully opaque
  })
  
  teethModel.traverse((child) => {
    if (child.isMesh && child.userData.isSelectable) {
      totalSelectableTeeth++
      const toothIndex = child.userData.toothIndex
      const isSelected = selectedTeeth.includes(toothIndex)
      
      // Dispose old material properly
      if (child.material && child.material !== child.userData.originalMaterial) {
        child.material.dispose()
      }
      
      if (isSelected) {
        // Apply grillz material to selected teeth
        child.material = createGrillzMaterial(currentMaterial)
        updatedCount++
      } else {
        // Always use fresh white tooth material for unselected teeth
        child.material = whiteToothMaterial.clone()
      }
      
      child.material.needsUpdate = true

      // Compute bounding box volume to aid later filtering
      if (child.geometry) {
        child.geometry.computeBoundingBox()
        const bb = child.geometry.boundingBox
        const vol = (bb.max.x - bb.min.x) * (bb.max.y - bb.min.y) * (bb.max.z - bb.min.z)
        child.userData.volume = vol
      }
    }
  })
  
  // Update visibility if the "show only selected" option is enabled
  if (showOnlySelected) {
    // Apply visibility without toggling the state
    applyVisibilitySettings()
  }
}

function updateGrillzMaterial() {
  // Update materials directly on selected teeth
  updateDirectToothMaterials()
}

function updatePrice() {
  const materialConfig = materialPrices[currentMaterial];
  const pricePerTooth = materialConfig ? materialConfig.price : 200;
  const totalPrice = selectedTeeth.length * pricePerTooth;
  
  const totalPriceEl = document.getElementById("totalPrice");
  if (totalPriceEl) totalPriceEl.textContent = Math.round(totalPrice);
}

function updateSummary() {
  const summaryMaterialEl = document.getElementById("summaryMaterial");
  const summaryTeethCountEl = document.getElementById("summaryTeethCount");
  
  if (summaryMaterialEl) {
    const materialConfig = materialPrices[currentMaterial];
    summaryMaterialEl.textContent = materialConfig ? materialConfig.name : currentMaterial;
  }
  
  if (summaryTeethCountEl) {
    summaryTeethCountEl.textContent = selectedTeeth.length;
  }
}

function resetCameraView() {
  if (controls && camera) {
    controls.reset()
    camera.position.set(0, 1, 6)
    controls.target.set(0, 0, 0)
  }
}

function toggleFullscreen() {
  const viewerElement = document.querySelector(".viewer-wrapper")
  if (!document.fullscreenElement) {
    viewerElement
      .requestFullscreen()
      .catch((err) => {
        // Silently handle fullscreen errors
      })
  } else {
    document.exitFullscreen()
  }
}

function onWindowResize() {
  const canvas = document.getElementById("threejs-canvas")
  if (!canvas) return
  const container = canvas.parentElement
  if (container && renderer && camera) {
    camera.aspect = container.clientWidth / container.clientHeight
    camera.updateProjectionMatrix()
    renderer.setSize(container.clientWidth, container.clientHeight)
  }
}

function animate() {
  requestAnimationFrame(animate)
  if (controls) controls.update()
  if (renderer && scene && camera) renderer.render(scene, camera)
}

// Step progression functions
function handleContinue() {
  if (currentStep === 1) {
    // Validate selection (at least one tooth selected)
    if (selectedTeeth.length === 0) {
      alert("Please select at least one tooth before continuing.");
      return;
    }
    goToStep(2);
  } else if (currentStep === 2) {
    // Validate form fields
    if (!validateOrderDetails()) {
      return;
    }
    updateFinalOverview();
    goToStep(3);
  } else if (currentStep === 3) {
    // Create order and redirect to payment
    createOrder();
  }
}

function handleBack() {
  if (currentStep > 1) {
    goToStep(currentStep - 1)
  }
}

function toggleInteractions(enabled) {
  // Enable/disable tooth selection
  const teeth = document.querySelectorAll(".tooth")
  teeth.forEach(tooth => {
    if (enabled) {
      tooth.style.pointerEvents = "auto"
      tooth.style.opacity = "1"
    } else {
      tooth.style.pointerEvents = "none"
      tooth.style.opacity = "0.6"
    }
  })

  // Enable/disable material selection
  const materialOptions = document.querySelectorAll(".material-option")
  materialOptions.forEach(option => {
    if (enabled) {
      option.style.pointerEvents = "auto"
      option.style.opacity = "1"
    } else {
      option.style.pointerEvents = "none"
      option.style.opacity = "0.6"
    }
  })

  // Enable/disable clear button
  const clearBtn = document.getElementById("clearSelection")
  if (clearBtn) {
    if (enabled) {
      clearBtn.style.pointerEvents = "auto"
      clearBtn.style.opacity = "1"
    } else {
      clearBtn.style.pointerEvents = "none"
      clearBtn.style.opacity = "0.6"
    }
  }

  // Store interaction state for 3D click handling
  window.interactionsEnabled = enabled
}

function goToStep(step) {
  // Hide current step
  const currentStepEl = document.getElementById(`step${currentStep}`)
  if (currentStepEl) {
    currentStepEl.style.display = "none"
  }

  // Show new step
  const newStepEl = document.getElementById(`step${step}`)
  if (newStepEl) {
    newStepEl.style.display = "block"
  }

  // Update progress indicator
  document.querySelectorAll(".progress-step").forEach((stepEl, index) => {
    if (index + 1 <= step) {
      stepEl.classList.add("active")
    } else {
      stepEl.classList.remove("active")
    }
  })

  // Update button text and back button visibility
  const continueBtn = document.getElementById("continueBtn")
  const backBtn = document.getElementById("backBtn")
  
  if (continueBtn) {
    if (step === 3) {
      continueBtn.innerHTML = '<i class="fas fa-credit-card"></i> Create Order'
    } else {
      continueBtn.innerHTML = '<i class="fas fa-arrow-right"></i> Continue'
    }
  }

  // Show/hide back button based on step
  if (backBtn) {
    if (step === 1) {
      backBtn.style.display = "none"
    } else {
      backBtn.style.display = "block"
    }
  }

  // Enable/disable interactions based on step
  toggleInteractions(step === 1)

  currentStep = step
}

function validateOrderDetails() {
  const fullName = document.getElementById("fullName")?.value?.trim();
  const address = document.getElementById("address")?.value?.trim();
  const city = document.getElementById("city")?.value?.trim();
  const zipCode = document.getElementById("zipCode")?.value?.trim();

  if (!fullName || !address || !city || !zipCode) {
    utils.showToast("Please fill in all shipping address fields.", "warning");
    return false;
  }

  // Store shipping data for later use
  window.shippingData = {
    shipping_full_name: fullName,
    shipping_address: address,
    shipping_city: city,
    shipping_zip_code: zipCode,
    payment_method: "crypto"
  };

  return true;
}

function updateFinalOverview() {
  // Update material
  const finalMaterialEl = document.getElementById("finalMaterial")
  if (finalMaterialEl) {
    const activeMaterialOpt = document.querySelector(".material-option.active .material-name")
    finalMaterialEl.textContent = activeMaterialOpt ? activeMaterialOpt.textContent : currentMaterial
  }

  // Update teeth count
  const finalTeethCountEl = document.getElementById("finalTeethCount")
  if (finalTeethCountEl) {
    finalTeethCountEl.textContent = selectedTeeth.length
  }

  // Update address
  const finalAddressEl = document.getElementById("finalAddress")
  if (finalAddressEl) {
    const fullName = document.getElementById("fullName").value.trim()
    const city = document.getElementById("city").value.trim()
    if (fullName && city) {
      finalAddressEl.textContent = `${fullName}, ${city}`
    }
  }

  // Update payment method
  const finalPaymentEl = document.getElementById("finalPayment")
  if (finalPaymentEl) {
    const activeCrypto = document.querySelector(".crypto-option.active .crypto-name")
    finalPaymentEl.textContent = activeCrypto ? activeCrypto.textContent : "Stripe"
  }

  // Update total price
  const finalTotalPriceEl = document.getElementById("finalTotalPrice")
  if (finalTotalPriceEl) {
    const materialConfig = materialPrices[currentMaterial];
    const pricePerTooth = materialConfig ? materialConfig.price : 200;
    const totalPrice = selectedTeeth.length * pricePerTooth
    finalTotalPriceEl.textContent = Math.round(totalPrice)
  }
}

window.createOrder = async function() {
    // Ensure user is authenticated
    const authToken = localStorage.getItem('authToken');
    if (!authToken) {
        window.location.href = '/auth/login';
        return;
    }
    
    // Disable button & show spinner
    const continueBtn = document.getElementById('continueBtn');
    const originalHTML = continueBtn.innerHTML;
    continueBtn.disabled = true;
    continueBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    
    try {
        // Create order with all data
        const orderRes = await utils.apiClient.post('/api/create-order', {
            product_type: 'grillz',
            material: currentMaterial,
            teeth_selection: selectedTeeth,
            shipping_full_name: document.getElementById('fullName')?.value?.trim(),
            shipping_address: document.getElementById('address')?.value?.trim(),
            shipping_city: document.getElementById('city')?.value?.trim(),
            shipping_zip_code: document.getElementById('zipCode')?.value?.trim()
        });
        
        console.log('Order response:', orderRes);
        
        if (!orderRes.success) {
            throw new Error(orderRes.message || 'Failed to create order');
        }
        
        // Check if we have Stripe checkout URL
        if (orderRes.client_secret) {
            // Success – redirect DIRECTLY to Stripe checkout
            utils.showToast('Order created! Redirecting to payment...', 'success', 1000);
            window.location.href = orderRes.client_secret;  // Direct redirect to Stripe
        } else {
            throw new Error('Payment processing not available');
        }
    } catch (err) {
        console.error('Order creation failed:', err);
        utils.showToast(err.message || 'Failed to create order', 'error');
        continueBtn.disabled = false;
        continueBtn.innerHTML = originalHTML;
    }
};

// Make scene globally available for material creation
window.scene = scene
