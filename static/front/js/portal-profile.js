// Self-Service Profile: small helpers only. Saving and every rule are on the server.
(function () {
    var form = document.getElementById('profileForm');
    if (!form) return;
    var status = document.getElementById('saveStatus');

    function markDirty() {
        status.innerHTML = '<i class="fa-regular fa-circle me-1"></i>Unsaved changes';
    }
    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);

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