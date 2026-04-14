(function () {
    const revealTargets = document.querySelectorAll('.panel, .main-panel, .section-card, .welcome, .metric, .table-responsive, .alert, .card');
    revealTargets.forEach(function (el, index) {
        el.classList.add('fx-reveal');
        el.style.transitionDelay = Math.min(index * 45, 300) + 'ms';
    });

    const io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('fx-in');
                io.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08 });

    revealTargets.forEach(function (el) { io.observe(el); });

    const glowTargets = document.querySelectorAll('.btn, .menu-link, .menu-btn');
    glowTargets.forEach(function (el) {
        el.addEventListener('pointerdown', function () {
            el.style.filter = 'saturate(1.05) brightness(1.02)';
        });
        el.addEventListener('pointerup', function () {
            el.style.filter = '';
        });
        el.addEventListener('pointerleave', function () {
            el.style.filter = '';
        });
    });
})();
