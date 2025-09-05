/**
 * Manual Mobile Testing Script
 * This script can be run in browser dev tools to test mobile responsiveness
 */

// Test viewport sizes
const viewports = [
  { name: 'iPhone SE', width: 320, height: 568 },
  { name: 'iPhone 8', width: 375, height: 667 },
  { name: 'iPhone 12 Pro', width: 414, height: 896 },
  { name: 'iPad Mini', width: 768, height: 1024 }
];

// Function to test responsive layout
function testResponsiveLayout() {
  const bodyScrollWidth = document.body.scrollWidth;
  const bodyClientWidth = document.body.clientWidth;
  const hasHorizontalOverflow = bodyScrollWidth > bodyClientWidth;
  
  console.log(`Screen width: ${window.innerWidth}px`);
  console.log(`Body scrollWidth: ${bodyScrollWidth}px`);
  console.log(`Body clientWidth: ${bodyClientWidth}px`);
  console.log(`Has horizontal overflow: ${hasHorizontalOverflow}`);
  
  // Check form container
  const formContainer = document.querySelector('.max-w-4xl');
  if (formContainer) {
    const formRect = formContainer.getBoundingClientRect();
    console.log(`Form container width: ${formRect.width}px`);
    console.log(`Form container left: ${formRect.left}px`);
    console.log(`Form fits in viewport: ${formRect.right <= window.innerWidth}`);
  }
  
  return !hasHorizontalOverflow;
}

// Function to test touch target sizes
function testTouchTargets() {
  const buttons = document.querySelectorAll('button');
  const minTouchSize = 44; // Apple's recommended minimum
  
  console.log(`Found ${buttons.length} buttons to test`);
  
  const undersizedButtons = [];
  buttons.forEach((button, index) => {
    if (button.offsetParent !== null) { // Only check visible buttons
      const rect = button.getBoundingClientRect();
      if (rect.width < minTouchSize || rect.height < minTouchSize) {
        undersizedButtons.push({
          index,
          width: rect.width,
          height: rect.height,
          text: button.textContent.trim().substring(0, 50)
        });
      }
    }
  });
  
  if (undersizedButtons.length > 0) {
    console.warn(`Found ${undersizedButtons.length} undersized buttons:`, undersizedButtons);
  } else {
    console.log('✅ All visible buttons meet minimum touch target size');
  }
  
  return undersizedButtons.length === 0;
}

// Function to test form accessibility
function testFormAccessibility() {
  const inputs = document.querySelectorAll('input, textarea, select');
  console.log(`Found ${inputs.length} form inputs to test`);
  
  let accessibilityIssues = 0;
  inputs.forEach((input, index) => {
    if (input.offsetParent !== null) { // Only check visible inputs
      const rect = input.getBoundingClientRect();
      
      // Check if input is too small for mobile
      if (rect.height < 40) {
        console.warn(`Input ${index} may be too small for touch: ${rect.height}px height`);
        accessibilityIssues++;
      }
      
      // Check if input has proper labeling
      const hasLabel = input.labels && input.labels.length > 0;
      const hasAriaLabel = input.getAttribute('aria-label');
      const hasPlaceholder = input.placeholder;
      
      if (!hasLabel && !hasAriaLabel && !hasPlaceholder) {
        console.warn(`Input ${index} lacks proper labeling`);
        accessibilityIssues++;
      }
    }
  });
  
  if (accessibilityIssues === 0) {
    console.log('✅ All form inputs pass accessibility checks');
  }
  
  return accessibilityIssues === 0;
}

// Function to test content overflow
function testContentOverflow() {
  const containers = document.querySelectorAll('.card, [class*="card"], .max-w-4xl');
  let overflowIssues = 0;
  
  containers.forEach((container, index) => {
    if (container.offsetParent !== null) {
      const rect = container.getBoundingClientRect();
      
      if (rect.right > window.innerWidth) {
        console.warn(`Container ${index} overflows viewport:`, {
          right: rect.right,
          viewportWidth: window.innerWidth,
          className: container.className
        });
        overflowIssues++;
      }
    }
  });
  
  if (overflowIssues === 0) {
    console.log('✅ No container overflow detected');
  }
  
  return overflowIssues === 0;
}

// Main test function
function runMobileUsabilityTests() {
  console.log('🔍 Running Mobile Usability Tests');
  console.log('================================');
  
  const results = {
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    responsiveLayout: testResponsiveLayout(),
    touchTargets: testTouchTargets(),
    formAccessibility: testFormAccessibility(),
    contentOverflow: testContentOverflow()
  };
  
  console.log('Test Results:', results);
  
  const allPassed = Object.values(results).slice(1).every(test => test === true);
  if (allPassed) {
    console.log('🎉 All mobile usability tests passed!');
  } else {
    console.warn('⚠️ Some mobile usability tests failed');
  }
  
  return results;
}

// Auto-run tests if script is executed
if (typeof window !== 'undefined') {
  // Add a delay to ensure page is fully loaded
  setTimeout(() => {
    if (window.location.pathname === '/projects/create') {
      runMobileUsabilityTests();
    } else {
      console.log('Navigate to /projects/create to run mobile tests');
    }
  }, 2000);
}

// Export for manual use
window.runMobileUsabilityTests = runMobileUsabilityTests;
window.testResponsiveLayout = testResponsiveLayout;
window.testTouchTargets = testTouchTargets;
window.testFormAccessibility = testFormAccessibility;
window.testContentOverflow = testContentOverflow;