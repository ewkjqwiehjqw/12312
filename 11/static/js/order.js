if (window.__orderJSLoaded) {
    console.warn('order.js already loaded – skipping duplicate execution.');
    return;
}
window.__orderJSLoaded = true;

// Order page functionality with 3D viewer and secure order management

// Global state
let orderData = {
    material: 'gold',
    teeth_selection: [],
    total_price: 0,
    shipping_full_name: '',
    shipping_address: '',
    shipping_city: '',
    shipping_zip_code: '',
    payment_method: 'card'
};

// Material pricing - loaded from server
let MATERIAL_PRICES = {};

// Order-specific variables
let teethMeshes = [];
let isSceneInitialized = false;
let supportedCryptos = [];
let currentStep = 1;

// Stripe variables
let stripe = null;
let cardElement = null;

// Wait for DOM and dependencies to be available
function initializeWhenReady() {
    if (window.utils && window.utils.apiClient) {
        console.log('Dependencies loaded, initializing order page...');
        initializeOrderPage();
    } else {
        console.log('Waiting for dependencies...');
        setTimeout(initializeWhenReady, 100);
    }
}

// Load prices from server
async function loadPrices() {
    try {
        const response = await fetch('/api/prices');
        if (!response.ok) throw new Error('Failed to fetch prices');
        const data = await response.json();
        
        // Convert server format to client format
        MATERIAL_PRICES = {};
        for (const [material, details] of Object.entries(data.materials)) {
            MATERIAL_PRICES[material] = details.price;
        }
        
        console.log('Loaded prices from server:', MATERIAL_PRICES);
    } catch (error) {
        console.error('Failed to load prices:', error);
        // Fallback prices (should match server)
        MATERIAL_PRICES = {
            gold: 299,
            silver: 149,
            diamond: 999
        };
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        await loadPrices();
        initializeWhenReady();
    });
} else {
    loadPrices().then(() => initializeWhenReady());
}

// Initialize the order page
function initializeOrderPage() {
    console.log('Initializing order page...');
    setupEventListeners();
    updateUI();
    initializeStripe();
}

// Create teeth meshes (simplified representation)
function createTeethMeshes() {
    // Use the scene from script.js
    if (!window.scene) {
        console.error('Scene not initialized in script.js');
        return;
    }

    const toothGeometry = new THREE.BoxGeometry(0.3, 0.4, 0.2);
    
    // Top row teeth (T1-T8)
    for (let i = 0; i < 8; i++) {
        const toothMaterial = new THREE.MeshPhongMaterial({ 
            color: 0xffffff,
            transparent: true,
            opacity: 0.9
        });
        
        const tooth = new THREE.Mesh(toothGeometry, toothMaterial);
        tooth.position.set((i - 3.5) * 0.4, 0.5, 0);
        tooth.userData = { toothNumber: i + 1, selected: false };
        tooth.castShadow = true;
        tooth.receiveShadow = true;
        
        window.scene.add(tooth);
        teethMeshes.push(tooth);
    }
    
    // Bottom row teeth (B1-B8)
    for (let i = 0; i < 8; i++) {
        const toothMaterial = new THREE.MeshPhongMaterial({ 
            color: 0xffffff,
            transparent: true,
            opacity: 0.9
        });
        
        const tooth = new THREE.Mesh(toothGeometry, toothMaterial);
        tooth.position.set((i - 3.5) * 0.4, -0.5, 0);
        tooth.userData = { toothNumber: i + 9, selected: false };
        tooth.castShadow = true;
        tooth.receiveShadow = true;
        
        window.scene.add(tooth);
        teethMeshes.push(tooth);
    }
}

// Setup event listeners
function setupEventListeners() {
    // Material selection
    document.querySelectorAll('.material-option').forEach(option => {
        option.addEventListener('click', function() {
            selectMaterial(this.dataset.material);
        });
    });

    // Teeth selection
    document.querySelectorAll('.tooth').forEach(tooth => {
        tooth.addEventListener('click', function() {
            toggleTooth(parseInt(this.dataset.tooth));
        });
    });

    // Clear selection
    document.getElementById('clearSelection')?.addEventListener('click', clearTeethSelection);

    // Navigation buttons
    document.getElementById('continueBtn')?.addEventListener('click', handleContinue);
    document.getElementById('backBtn')?.addEventListener('click', handleBack);

    // Payment method selection
    document.querySelectorAll('.payment-option').forEach(option => {
        option.addEventListener('click', function() {
            selectPaymentMethod(this.dataset.payment);
        });
    });

    // Form inputs for step 2
    ['fullName', 'address', 'city', 'zipCode'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', function() {
                switch (id) {
                    case 'fullName':
                        orderData.shipping_full_name = this.value.trim();
                        break;
                    case 'zipCode':
                        orderData.shipping_zip_code = this.value.trim();
                        break;
                    case 'address':
                        orderData.shipping_address = this.value.trim();
                        break;
                    case 'city':
                        orderData.shipping_city = this.value.trim();
                        break;
                }
                updateFinalSummary();
            });
        }
    });

    // 3D viewer controls
    document.getElementById('resetView')?.addEventListener('click', resetCameraView);
    document.getElementById('fullscreen')?.addEventListener('click', toggleFullscreen);
    document.getElementById('hideUnselected')?.addEventListener('click', toggleUnselectedTeeth);

    // Modal close handlers
    const modal = document.getElementById('loginModal');
    if (modal) {
        const closeBtn = modal.querySelector('.close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => modal.style.display = 'none');
        }
        
        window.addEventListener('click', function(event) {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
}

// Material selection
function selectMaterial(material) {
    if (!MATERIAL_PRICES[material]) return;
    
    orderData.material = material;
    
    // Update UI
    document.querySelectorAll('.material-option').forEach(option => {
        option.classList.remove('active');
    });
    document.querySelector(`[data-material="${material}"]`).classList.add('active');
    
    // Update 3D visualization
    updateTeethMaterial(material);
    
    // Update pricing
    calculatePrice();
    updateUI();
}

// Toggle tooth selection
function toggleTooth(toothNumber) {
    const index = orderData.teeth_selection.indexOf(toothNumber);
    
    if (index > -1) {
        // Remove tooth
        orderData.teeth_selection.splice(index, 1);
    } else {
        // Add tooth
        orderData.teeth_selection.push(toothNumber);
    }
    
    // Update UI
    updateTeethSelection();
    calculatePrice();
    updateUI();
}

// Clear teeth selection
function clearTeethSelection() {
    orderData.teeth_selection = [];
    updateTeethSelection();
    calculatePrice();
    updateUI();
}

// Update teeth selection UI
function updateTeethSelection() {
    // Update 2D selector
    document.querySelectorAll('.tooth').forEach(tooth => {
        const toothNumber = parseInt(tooth.dataset.tooth);
        if (orderData.teeth_selection.includes(toothNumber)) {
            tooth.classList.add('selected');
        } else {
            tooth.classList.remove('selected');
        }
    });
    
    // Update 3D meshes
    if (isSceneInitialized) {
        teethMeshes.forEach(mesh => {
            if (orderData.teeth_selection.includes(mesh.userData.toothNumber)) {
                mesh.userData.selected = true;
                updateToothMaterial(mesh, orderData.material);
            } else {
                mesh.userData.selected = false;
                mesh.material.color.setHex(0xffffff);
            }
        });
    }
}

// Update tooth material in 3D
function updateToothMaterial(mesh, material) {
    let color;
    switch (material) {
        case 'gold':
            color = 0xFFD700;
            break;
        case 'silver':
            color = 0xC0C0C0;
            break;
        case 'diamond':
            color = 0xE6E6FA;
            break;
        default:
            color = 0xffffff;
    }
    mesh.material.color.setHex(color);
}

// Update all teeth materials
function updateTeethMaterial(material) {
    if (!isSceneInitialized) return;
    
    teethMeshes.forEach(mesh => {
        if (mesh.userData.selected) {
            updateToothMaterial(mesh, material);
        }
    });
}

// Calculate price
function calculatePrice() {
    const basePrice = MATERIAL_PRICES[orderData.material] || 0;
    const teethCount = orderData.teeth_selection.length;
    orderData.total_price = basePrice * teethCount;
}

// Update UI elements
function updateUI() {
    // Update summary
    document.getElementById('summaryMaterial').textContent = 
        orderData.material.charAt(0).toUpperCase() + orderData.material.slice(1);
    document.getElementById('summaryTeethCount').textContent = orderData.teeth_selection.length;
    document.getElementById('totalPrice').textContent = orderData.total_price;
    
    // Update continue button state
    const continueBtn = document.getElementById('continueBtn');
    if (currentStep === 1) {
        continueBtn.disabled = orderData.teeth_selection.length === 0;
    }
}

// Handle continue button
async function handleContinue() {
    if (currentStep === 1) {
        if (orderData.teeth_selection.length === 0) {
            utils.showToast('Please select at least one tooth', 'warning');
            return;
        }
        nextStep();
    } else if (currentStep === 2) {
        if (!validateShippingForm()) {
            return;
        }
        nextStep();
    } else if (currentStep === 3) {
        await finalizeOrder();
    }
}

// Handle back button
function handleBack() {
    if (currentStep > 1) {
        previousStep();
    }
}

// Validate shipping form
function validateShippingForm() {
    const requiredFields = ['fullName', 'address', 'city', 'zipCode'];
    let isValid = true;
    
    requiredFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (!field || !field.value.trim()) {
            field?.classList.add('error');
            isValid = false;
        } else {
            field?.classList.remove('error');
            switch (fieldId) {
                case 'fullName':
                    orderData.shipping_full_name = field.value.trim();
                    break;
                case 'zipCode':
                    orderData.shipping_zip_code = field.value.trim();
                    break;
                case 'address':
                    orderData.shipping_address = field.value.trim();
                    break;
                case 'city':
                    orderData.shipping_city = field.value.trim();
                    break;
            }
        }
    });
    
    if (!isValid) {
        utils.showToast('Please fill in all shipping information', 'warning');
    }
    
    return isValid;
}

// Navigation functions
function nextStep() {
    if (currentStep < 3) {
        currentStep++;
        updateStepDisplay();
        updateFinalSummary();
    }
}

function previousStep() {
    if (currentStep > 1) {
        currentStep--;
        updateStepDisplay();
    }
}

// Update step display
function updateStepDisplay() {
    // Hide all step contents
    document.querySelectorAll('.step-content').forEach(content => {
        content.style.display = 'none';
    });
    
    // Show current step
    const currentContent = document.getElementById(`step${currentStep}`);
    if (currentContent) {
        currentContent.style.display = 'block';
    }
    
    // Update progress indicator
    document.querySelectorAll('.progress-step').forEach((step, index) => {
        if (index + 1 <= currentStep) {
            step.classList.add('active');
        } else {
            step.classList.remove('active');
        }
    });
    
    // Update buttons
    const backBtn = document.getElementById('backBtn');
    const continueBtn = document.getElementById('continueBtn');
    
    if (backBtn) {
        backBtn.style.display = currentStep > 1 ? 'block' : 'none';
    }
    
    if (continueBtn) {
        const btnText = continueBtn.querySelector('.btn-text') || continueBtn;
        if (currentStep === 3) {
            btnText.innerHTML = '<i class="fas fa-check"></i> Place Order';
        } else {
            btnText.innerHTML = '<i class="fas fa-arrow-right"></i> Continue';
        }
    }
}

// Select payment method
function selectPaymentMethod(method) {
    orderData.payment_method = method;
    
    document.querySelectorAll('.payment-option').forEach(option => {
        option.classList.remove('active');
    });
    document.querySelector(`[data-payment="${method}"]`).classList.add('active');
    
    updateFinalSummary();
}

// Update final summary
function updateFinalSummary() {
    document.getElementById('finalMaterial').textContent = 
        orderData.material.charAt(0).toUpperCase() + orderData.material.slice(1);
    document.getElementById('finalTeethCount').textContent = orderData.teeth_selection.length;
    document.getElementById('finalTotalPrice').textContent = orderData.total_price;
    
    const address = `${orderData.shipping_full_name || ''} ${orderData.shipping_address || ''}`.trim();
    document.getElementById('finalAddress').textContent = address || '-';
    
    document.getElementById('finalPayment').textContent = 'Credit Card (Stripe)';
}

// Finalize order
async function finalizeOrder() {
    const continueBtn = document.getElementById('continueBtn');
    const btnText = continueBtn.querySelector('.btn-text') || continueBtn;
    const originalText = btnText.innerHTML;
    
    try {
        // Show loading state
        continueBtn.disabled = true;
        btnText.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        
        // Check authentication
        const authToken = localStorage.getItem('authToken');
        if (!authToken) {
            window.location.href = '/auth/login';
            return;
        }
        
        // Ensure latest shipping values are captured
        orderData.shipping_full_name = document.getElementById('fullName')?.value.trim() || orderData.shipping_full_name;
        orderData.shipping_address = document.getElementById('address')?.value.trim() || orderData.shipping_address;
        orderData.shipping_city = document.getElementById('city')?.value.trim() || orderData.shipping_city;
        orderData.shipping_zip_code = document.getElementById('zipCode')?.value.trim() || orderData.shipping_zip_code;

        // Prepare order data
        const orderPayload = {
            product_type: 'grillz',
            material: orderData.material,
            teeth_selection: orderData.teeth_selection,
            shipping_full_name: orderData.shipping_full_name,
            shipping_address: orderData.shipping_address,
            shipping_city: orderData.shipping_city,
            shipping_zip_code: orderData.shipping_zip_code,
            payment_method: orderData.payment_method
        };
        console.log('Order payload', orderPayload);
        
        // Create order and obtain Stripe client secret
        const orderRes = await utils.apiClient.post('/api/create-order', orderPayload);

        const clientSecret = orderRes.client_secret;

        if (!stripe || !cardElement) {
            utils.showToast('Payment form not initialized', 'error');
            return;
        }

        // Confirm the card payment
        const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
            payment_method: {
                card: cardElement,
                billing_details: {
                    name: orderData.shipping_full_name,
                    address: {
                        line1: orderData.shipping_address,
                        postal_code: orderData.shipping_zip_code,
                        city: orderData.shipping_city
                    }
                }
            }
        });

        if (error) {
            console.error('Stripe payment error:', error);
            utils.showToast(error.message || 'Payment failed', 'error');
            return;
        }

        utils.showToast('Payment successful! Redirecting...', 'success');
        window.location.href = `/invoice/success?payment_intent=${paymentIntent.id}`;
    } catch (error) {
        console.error('Order creation failed:', error);
        utils.showToast(error.message || 'Failed to create order', 'error');
    } finally {
        // Reset button state
        continueBtn.disabled = false;
        btnText.innerHTML = originalText;
    }
}

// 3D viewer controls
function resetCameraView() {
    if (camera && controls) {
        camera.position.set(0, 0, 5);
        controls.reset();
    }
}

function toggleFullscreen() {
    const container = document.querySelector('.viewer-container');
    if (!document.fullscreenElement) {
        container.requestFullscreen().catch(err => {
            console.log('Fullscreen error:', err);
        });
    } else {
        document.exitFullscreen();
    }
}

function toggleUnselectedTeeth() {
    if (!isSceneInitialized) return;
    
    const btn = document.getElementById('hideUnselected');
    const isHiding = btn.classList.contains('hiding');
    
    teethMeshes.forEach(mesh => {
        if (!mesh.userData.selected) {
            mesh.visible = isHiding;
        }
    });
    
    btn.classList.toggle('hiding');
    btn.title = isHiding ? 'Hide unselected teeth' : 'Show all teeth';
}

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    
    if (controls) {
        controls.update();
    }
    
    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
}

// Handle window resize
function onWindowResize() {
    if (!camera || !renderer) return;
    
    const canvas = document.getElementById('threejs-canvas');
    const container = canvas.parentElement;
    const width = container.clientWidth;
    const height = container.clientHeight;
    
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
}

// Export for global access
window.orderManager = {
    initializeOrderPage,
    selectMaterial,
    toggleTooth,
    clearTeethSelection,
    calculatePrice,
    nextStep,
    previousStep,
    finalizeOrder
};


// Export for global access
window.orderState = orderData;

// Ensure global createOrder always uses orderManager
window.createOrder = async function() {
    if (window.orderManager && typeof window.orderManager.finalizeOrder === 'function') {
        return window.orderManager.finalizeOrder();
    }
    console.warn('Order manager not ready, please retry after initialization.');
    alert('Initializing... please click again in a second.');
};

// ---------------------------------------------------------------------------
// Stripe Initialization
// ---------------------------------------------------------------------------

async function initializeStripe() {
    try {
        const pricingRes = await utils.apiClient.get('/api/prices');
        const publishableKey = pricingRes.stripe_publishable_key;
        if (!publishableKey) {
            console.error('Stripe publishable key missing');
            return;
        }
        stripe = Stripe(publishableKey);
        const elements = stripe.elements();
        cardElement = elements.create('card');
        cardElement.mount('#stripe-payment-element');
    } catch (err) {
        console.error('Failed to initialize Stripe:', err);
        utils.showToast('Failed to initialize payment form', 'error');
    }
} 