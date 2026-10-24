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
    form.addEventListener('submit', function () {
        dirty = false;
        // Show progress while the page saves, especially when photos are going up
        var uploading = form.querySelectorAll('.photo-tile input[type="file"]');
        var withPhotos = Array.prototype.some.call(uploading, function (i) { return i.files.length; });
        status.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>' +
            (withPhotos ? 'Saving your photos… please keep this page open' : 'Saving…');
        Array.prototype.forEach.call(uploading, function (i) {
            if (i.files.length) i.closest('.photo-tile').classList.add('is-uploading');
        });
        // Disable after the browser has taken the clicked button's value
        setTimeout(function () {
            document.querySelectorAll('button[form="profileForm"]').forEach(function (b) { b.disabled = true; });
        }, 0);
    });
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

    // ---------- Photos: shrink on the phone before uploading, then preview
    // A 10 MB phone photo becomes ~200–400 KB, so uploads take seconds on mobile data.
    // The server still resizes and cleans every photo, so this is only about speed.
    var PHOTO_MAX_EDGE = 1600, PHOTO_QUALITY = 0.8;
    var saveButtons = document.querySelectorAll('button[form="profileForm"]');
    var pending = 0;

    function setBusy(busy) {
        pending += busy ? 1 : -1;
        saveButtons.forEach(function (b) { b.disabled = pending > 0; });
        if (pending > 0) status.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Preparing photo…';
        else markDirty();
    }

    function shrink(file) {
        // Resolves with a smaller JPEG File, or the original if the browser can't read it (e.g. HEIC)
        if (!window.createImageBitmap || !window.DataTransfer) return Promise.resolve(file);
        return createImageBitmap(file, { imageOrientation: 'from-image' }).then(function (bitmap) {
            var scale = Math.min(1, PHOTO_MAX_EDGE / Math.max(bitmap.width, bitmap.height));
            var canvas = document.createElement('canvas');
            canvas.width = Math.round(bitmap.width * scale);
            canvas.height = Math.round(bitmap.height * scale);
            canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            if (bitmap.close) bitmap.close();
            return new Promise(function (resolve) {
                canvas.toBlob(function (blob) {
                    if (!blob || blob.size >= file.size) return resolve(file);  // never make it bigger
                    var name = file.name.replace(/\.[^.]+$/, '') + '.jpg';
                    resolve(new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() }));
                }, 'image/jpeg', PHOTO_QUALITY);
            });
        }).catch(function () { return file; });
    }

    form.querySelectorAll('.photo-tile input[type="file"]').forEach(function (input) {
        input.addEventListener('change', function () {
            var file = input.files[0];
            if (!file) return;
            var tile = input.closest('.photo-tile');
            setBusy(true);
            shrink(file).then(function (smaller) {
                if (smaller !== file) {
                    var dt = new DataTransfer();
                    dt.items.add(smaller);
                    input.files = dt.files;  // the form now uploads the small version
                }
                tile.style.backgroundImage = 'url(' + URL.createObjectURL(smaller) + ')';
                tile.classList.add('filled');
                setBusy(false);
            });
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