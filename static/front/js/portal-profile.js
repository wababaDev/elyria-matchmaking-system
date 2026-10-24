// Self-Service Profile: small helpers only. Saving and every rule are on the server.
(function () {
    var form = document.getElementById('profileForm');
    if (!form) return;
    var status = document.getElementById('saveStatus');

    // ---------- Unsaved changes: mark them, and warn before leaving the page
    var dirty = false;
    function markDirty() {
        dirty = true;
        status.innerHTML = '<i class="fa-regular fa-circle me-1"></i>Unsaved changes';
    }
    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);
    form.addEventListener('submit', function () { dirty = false; });  // Save / Mark complete
    window.addEventListener('beforeunload', function (e) {
        if (!dirty) return;
        e.preventDefault();
        e.returnValue = '';  // the browser shows its own "Leave site?" message
    });

    // ---------- Where the content starts below the sticky header (and the phone "jump to" bar)
    var header = document.querySelector('.portal-header');
    var jump = document.getElementById('sectionJump');
    var jumpBar = jump ? jump.closest('.section-jump') : null;

    function headerHeight() { return header ? header.offsetHeight : 0; }
    function topOffset() {
        var bar = jumpBar && jumpBar.offsetParent !== null ? jumpBar.offsetHeight : 0;  // 0 when hidden (desktop)
        return headerHeight() + bar + 16;
    }
    function setHeaderVar() {
        document.documentElement.style.setProperty('--portal-header-h', headerHeight() + 'px');
    }
    setHeaderVar();
    window.addEventListener('resize', setHeaderVar);

    // ---------- Highlight the section on screen (side nav on desktop, jump list on phones)
    var navLinks = document.querySelectorAll('.section-nav a[href^="#"]');
    var targets = Array.prototype.map.call(navLinks, function (a) {
        return document.querySelector(a.getAttribute('href'));
    });
    function spy() {
        var current = 0, limit = topOffset() + 20;
        targets.forEach(function (section, i) {
            if (section && section.getBoundingClientRect().top <= limit) current = i;
        });
        // Scrolled to the very bottom: the last section wins, even if it's short
        if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
            current = targets.length - 1;
        }
        navLinks.forEach(function (a, i) { a.classList.toggle('active', i === current); });
        if (jump && targets[current]) jump.value = targets[current].id;
    }
    window.addEventListener('scroll', spy, { passive: true });
    spy();

    // Phones: pick a section from the list to jump to it
    if (jump) {
        jump.addEventListener('change', function () {
            var target = document.getElementById(jump.value);
            if (!target) return;
            var y = target.getBoundingClientRect().top + window.scrollY - topOffset();
            window.scrollTo({ top: y, behavior: 'smooth' });
        });
    }

    // ---------- After "Mark complete" with gaps: go straight to the first empty answer
    var firstMissing = form.querySelector('.is-missing');
    if (firstMissing) {
        setTimeout(function () {
            var y = firstMissing.getBoundingClientRect().top + window.scrollY - topOffset();
            window.scrollTo({ top: y, behavior: 'smooth' });
        }, 300);
    }
    // Answering a highlighted question clears its highlight straight away
    form.addEventListener('input', clearMissing);
    form.addEventListener('change', clearMissing);
    function clearMissing(e) {
        var box = e.target.closest('.is-missing');
        if (!box) return;
        box.classList.remove('is-missing');
        var note = box.querySelector('.missing-note');
        if (note) note.remove();
    }

    // Children: the detail fields only show when "Yes"
    form.addEventListener('change', function (e) {
        if (e.target.name !== 'has_children') return;
        var show = e.target.value === 'yes';
        form.querySelectorAll('[data-children-detail]').forEach(function (el) { el.hidden = !show; });
    });

    // Photo tiles: preview the chosen file before it's saved
    form.querySelectorAll('.photo-tile input[type="file"]').forEach(function (input) {
        input.addEventListener('change', function () {
            var file = input.files[0];
            if (!file) return;
            var tile = input.closest('.photo-tile');
            tile.style.backgroundImage = 'url(' + URL.createObjectURL(file) + ')';
            tile.classList.add('filled');
        });
    });

    // Non-negotiables, capped (the server checks the cap too)
    var list = document.getElementById('nnList');
    var addBtn = document.getElementById('nnAdd');
    var counter = document.getElementById('nnCounter');
    if (!list) return;
    var MAX = parseInt(list.dataset.max, 10) || 5;

    function refresh() {
        var n = list.children.length;
        counter.textContent = n + ' of ' + MAX + ' used';
        counter.classList.toggle('full', n >= MAX);
        addBtn.disabled = n >= MAX;
    }

    function wire(row) {
        row.querySelector('button').addEventListener('click', function () {
            row.remove();
            refresh();
            markDirty();
        });
    }

    function addRow() {
        var row = document.createElement('div');
        row.className = 'nn-item';
        row.innerHTML = '<input type="text" name="non_negotiables" maxlength="200" placeholder="e.g. Must not smoke">' +
            '<button type="button" aria-label="Remove">&times;</button>';
        list.appendChild(row);
        wire(row);
        refresh();
        return row;
    }

    addBtn.addEventListener('click', function () {
        if (list.children.length >= MAX) return;
        addRow().querySelector('input').focus();
        markDirty();
    });

    Array.prototype.forEach.call(list.children, wire);
    if (!list.children.length) addRow();  // start with one empty row, like the design
    refresh();
})();