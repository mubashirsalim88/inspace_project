// app/static/js/scripts.js
document.addEventListener("DOMContentLoaded", function () {
    // Sidebar toggle
    const toggleButton = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("sidebar");
    if (toggleButton && sidebar) {
        toggleButton.addEventListener("click", () => {
            sidebar.classList.toggle("collapsed");
        });
    }

    // Three.js Starfield for login/signup
    const canvas = document.getElementById("bgCanvas");
    if (canvas) {
        let scene = new THREE.Scene();
        let camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        let renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true });
        renderer.setSize(window.innerWidth, window.innerHeight);

        let starsGeometry = new THREE.BufferGeometry();
        let starsMaterial = new THREE.PointsMaterial({ color: 0xffffff });
        let starsVertices = [];
        for (let i = 0; i < 1000; i++) {
            let x = (Math.random() - 0.5) * 2000;
            let y = (Math.random() - 0.5) * 2000;
            let z = (Math.random() - 0.5) * 2000;
            starsVertices.push(x, y, z);
        }
        starsGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starsVertices, 3));
        let stars = new THREE.Points(starsGeometry, starsMaterial);
        scene.add(stars);
        camera.position.z = 500;

        function animate() {
            requestAnimationFrame(animate);
            stars.rotation.y += 0.0005;
            renderer.render(scene, camera);
        }
        animate();
    }
});