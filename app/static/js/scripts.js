document.addEventListener("DOMContentLoaded", function () {
    // Sidebar Toggle
    const sidebar = document.getElementById('sidebar');
    const toggleButton = document.getElementById('sidebar-toggle');
    if (sidebar && toggleButton) {
        toggleButton.addEventListener('click', () => {
            sidebar.classList.toggle('-translate-x-full');
        });
    }

    // Notification Unread Count
    function updateUnreadCount() {
        const unreadCountElement = document.getElementById('unread-count');
        if (unreadCountElement) {
            fetch('/notification/unread_count')
                .then(response => response.json())
                .then(data => {
                    unreadCountElement.textContent = data.unread_count;
                    unreadCountElement.classList.toggle('hidden', data.unread_count === 0);
                })
                .catch(error => console.error('Error fetching unread count:', error));
        }
    }
    updateUnreadCount();
    setInterval(updateUnreadCount, 10000);
    document.addEventListener('messageRead', updateUnreadCount);

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