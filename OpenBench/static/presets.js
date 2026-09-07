let presetState = JSON.parse(document.getElementById('json-presets').textContent);
let presetKind = 'TEST';
let selectedPreset = null;
let presetBusy = false;
let presetDraft = [];
const editedFields = new Set();
const presetGroups = [
    ['test_mode', 'test_bounds', 'test_confidence', 'test_max_games'],
    ['scale_method', 'scale_nps'],
    ['dev_branch', 'dev_bench'],
    ['base_branch', 'base_bench'],
    ['base_engine', 'base_repo', 'base_network'],
    ['dev_engine', 'dev_repo', 'dev_network'],
];

function engine_presets(engine = get_dev_engine()) {
    const rows = presetState.presets.filter(p => p.engine === engine);
    return [...rows.filter(p => p.scope === 'engine'), ...rows.filter(p => p.scope === 'personal')];
}

function get_presets(engine, name) {
    const shared = engine_presets(engine).filter(p => p.scope === 'engine');
    return (shared.find(p => p.name === name) || (name === 'default' ? shared[0] : null))?.settings || {};
}

function expanded_settings(settings) {
    const result = {};
    for (const [key, value] of Object.entries(settings)) {
        if (key.startsWith('both_')) {
            result[key.replace('both_', 'dev_')] = value;
            if (presetKind !== 'TUNE') result[key.replace('both_', 'base_')] = value;
        }
    }
    for (const [key, value] of Object.entries(settings)) if (!key.startsWith('both_')) result[key] = value;
    if (!result.test_mode) {
        if (Number(result.test_max_games) > 0) result.test_mode = 'GAMES';
        else if (result.test_bounds && result.test_bounds !== 'N/A') result.test_mode = 'SPRT';
    }
    return result;
}

function preset_defaults() {
    const values = {};
    for (const name of presetState.fields) {
        const field = document.getElementById(name);
        if (!field) continue;
        values[name] = field.tagName === 'SELECT' ? (Array.from(field.options).find(option => option.defaultSelected) || field.options[0])?.value || '' : field.defaultValue;
    }
    for (const target of presetKind === 'TUNE' ? ['dev'] : ['dev', 'base']) {
        const engine = document.getElementById(target + '_engine').value;
        values[target + '_repo'] = repos[engine] || config.engines[engine]?.source || '';
        values[target + '_network'] = networks.find(network => network.engine === engine && network.default)?.sha256 || '';
    }
    if (presetKind !== 'TUNE') values.base_engine = get_base_engine();
    values.scale_method = presetKind === 'TUNE' ? 'DEV' : 'BASE';
    values.scale_nps = config.engines[presetKind === 'TUNE' ? get_dev_engine() : get_base_engine()]?.nps || '';
    return values;
}

function match_base_resources() {
    if (presetKind === 'TUNE' || get_dev_engine() === get_base_engine() || editedFields.has('base_options')) return;
    const dev = document.getElementById('dev_options').value;
    const base = document.getElementById('base_options');
    for (const name of ['Threads', 'Hash']) {
        const pattern = new RegExp('\\b' + name + '\\s*=\\s*\\d+\\b', 'gi');
        const value = dev.match(new RegExp('\\b' + name + '\\s*=\\s*(\\d+)\\b', 'i'))?.[1];
        if (value === undefined) continue;
        const option = name + '=' + value;
        base.value = pattern.test(base.value) ? base.value.replace(pattern, option) : (base.value + ' ' + option).trim();
    }
}

function apply_settings(settings) {
    const explicit = expanded_settings(settings);
    let retained = 0;
    if (presetKind !== 'TUNE' && explicit.base_engine && explicit.base_engine !== get_base_engine() && !editedFields.has('base_engine') && config.engines[explicit.base_engine]) set_engine(explicit.base_engine, 'base');
    const values = {...preset_defaults(), ...explicit};
    for (const [key, value] of Object.entries(values)) {
        const field = document.getElementById(key);
        if (!field || key === 'dev_engine') continue;
        const crossEngine = presetKind !== 'TUNE' && get_base_engine() !== get_dev_engine();
        const wrongBase = presetKind !== 'TUNE' && explicit.base_engine && explicit.base_engine !== get_base_engine();
        const protectedBase = (wrongBase || (crossEngine && !explicit.base_engine)) && ['base_options', 'base_branch', 'base_bench', 'base_network', 'base_repo'].includes(key);
        if (editedFields.has(key) || protectedBase) { if (editedFields.has(key) && key in explicit && field.value !== String(value)) retained++; continue; }
        if (field.tagName === 'SELECT') {
            const option = Array.from(field.options).find(option => option.value === String(value) || option.text === String(value));
            if (option) field.value = option.value;
        } else field.value = value;
    }
    if (!explicit.base_engine) match_base_resources();
    const mode = document.getElementById('test_mode');
    if (mode && values.test_mode && !editedFields.has('test_mode')) {
        if (mode.value === 'GAMES') {
            document.getElementById('test_bounds').value = 'N/A';
            document.getElementById('test_confidence').value = 'N/A';
        } else document.getElementById('test_max_games').value = 'N/A';
    }
    return retained;
}

function select_preset(preset) {
    selectedPreset = preset;
    const retained = apply_settings(preset.settings);
    render_presets();
    const message = document.getElementById('preset-message');
    message.replaceChildren();
    if (retained) {
        const text = document.createElement('span');
        text.textContent = 'Your edited fields were kept.';
        const overwrite = preset_button('Overwrite?', () => {
            editedFields.clear();
            apply_settings(preset.settings);
            render_presets();
            message.replaceChildren();
        }, 'Overwrite edited fields with this preset');
        const dismiss = preset_button('\u00d7', () => message.replaceChildren(), 'Dismiss preset notice');
        dismiss.className = 'preset-notice-dismiss';
        message.append(text, overwrite, dismiss);
    }
}

function preset_button(text, action, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.onclick = action;
    if (label) { button.title = label; button.setAttribute('aria-label', label); }
    return button;
}

function render_presets() {
    const root = document.getElementById('preset-slots');
    root.replaceChildren();
    const rows = engine_presets();
    for (const scope of ['engine', 'personal']) {
        const presets = rows.filter(preset => preset.scope === scope);
        if (!presets.length) continue;
        const group = document.createElement('div');
        group.className = 'preset-group';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-labelledby', 'preset-label-' + scope);
        const label = document.createElement('div');
        label.id = 'preset-label-' + scope;
        label.className = 'preset-group-label';
        label.textContent = scope === 'engine' ? get_dev_engine() + ' presets' : 'My presets';
        const buttons = document.createElement('div');
        buttons.className = 'preset-group-buttons';
        for (const preset of presets) {
            const button = preset_button(preset.name, () => select_preset(preset));
            button.className = 'anchorbutton btn-start';
            button.setAttribute('aria-pressed', String(selectedPreset?.id === preset.id));
            button.title = (preset.scope === 'engine' ? get_dev_engine() : 'Personal') + (preset.id === rows[0].id ? ' - Default preset' : '');
            buttons.append(button);
        }
        for (let index = presets.length; index % 4 !== 0; index++) {
            const slot = document.createElement('div');
            slot.className = 'preset-empty-slot';
            slot.setAttribute('aria-hidden', 'true');
            buttons.append(slot);
        }
        group.append(label, buttons);
        root.append(group);
    }
    document.getElementById('preset-manage-open').hidden = !rows.some(p => p.editable);
    document.getElementById('preset-save-open').disabled = !config.engines[get_dev_engine()];
}

function change_engine(engine, target, kind) {
    document.getElementById('preset-message').replaceChildren();
    presetKind = kind;
    if (!config.engines[engine]) engine = document.getElementById(target + '_engine')?.value;
    if (!config.engines[engine]) return;
    set_engine(engine, target);
    if (target === 'dev' && kind !== 'TUNE' && !editedFields.has('base_engine')) set_engine(engine, 'base');
    if (!editedFields.has('scale_nps')) set_option('scale_nps', config.engines[engine].nps);
    if (!editedFields.has('scale_method')) set_option('scale_method', kind === 'TUNE' ? 'DEV' : 'BASE');
    if (target === 'base') {
        const defaults = expanded_settings(get_presets(engine, 'default'));
        for (const key of ['options', 'branch', 'network']) {
            const field = 'base_' + key;
            if (!editedFields.has(field) && defaults[field] !== undefined) set_option(field, defaults[field]);
        }
        match_base_resources();
        return;
    }
    selectedPreset = null;
    const first = engine_presets(engine)[0];
    if (first) select_preset(first);
    else { apply_settings({}); render_presets(); }
}

function capture_preset() {
    const settings = {};
    for (const name of presetState.fields) {
        const field = document.getElementById(name);
        if (field && !field.disabled) settings[name] = field.value;
    }
    return settings;
}

function preset_scopes(select) {
    select.replaceChildren();
    if (presetState.editable[get_dev_engine()]) select.add(new Option(get_dev_engine() + ' - Shared presets', 'engine'));
    select.add(new Option('My presets', 'personal'));
    select.disabled = false;
}

function save_slots() {
    const scope = document.getElementById('preset-save-scope').value;
    const select = document.getElementById('preset-save-slot');
    select.replaceChildren(new Option('New preset', ''));
    for (const row of engine_presets().filter(p => p.scope === scope && p.editable)) select.add(new Option(row.name, row.id));
    select.value = '';
    save_slot_name();
}

function save_slot_name() {
    const row = engine_presets().find(p => p.id === document.getElementById('preset-save-slot').value);
    document.getElementById('preset-save-name').value = row?.name || '';
    document.getElementById('preset-save-submit').textContent = row ? 'Replace preset' : 'Save preset';
}

function render_preset_editor() {
    const root = document.getElementById('preset-editor');
    root.replaceChildren();
    if (!presetDraft.length) {
        const empty = document.createElement('p');
        empty.textContent = 'No presets.';
        root.append(empty);
    }
    for (const [index, preset] of presetDraft.entries()) {
        const row = document.createElement('div');
        row.className = 'preset-edit-row';
        const position = document.createElement('span');
        position.textContent = index + 1;
        const input = document.createElement('input');
        input.value = preset.name;
        input.maxLength = 128;
        input.required = true;
        input.setAttribute('aria-label', 'Preset ' + (index + 1) + ' name');
        input.oninput = () => { preset.name = input.value; document.getElementById('preset-manage-scope').disabled = true; };
        row.append(position, input);
        for (const [delta, text, label] of [[-1, '\u2191', 'Move up'], [1, '\u2193', 'Move down']]) {
            const button = preset_button(text, () => {
                const target = index + delta;
                [presetDraft[index], presetDraft[target]] = [presetDraft[target], presetDraft[index]];
                document.getElementById('preset-manage-scope').disabled = true;
                render_preset_editor();
            }, label + ': ' + preset.name);
            button.disabled = index + delta < 0 || index + delta >= presetDraft.length;
            row.append(button);
        }
        const remove = preset_button('\u00d7', () => {
            presetDraft.splice(index, 1);
            document.getElementById('preset-manage-scope').disabled = true;
            render_preset_editor();
        }, 'Delete: ' + preset.name);
        row.append(remove);
        root.append(row);
    }
}

async function save_presets(dialog, payload) {
    if (presetBusy) return;
    presetBusy = true;
    dialog.querySelector('.preset-error').textContent = '';
    const submit = dialog.querySelector('[type=submit]');
    submit.disabled = true;
    try {
        const response = await fetch('/presets/' + presetKind + '/', {method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value},
            body: JSON.stringify({...payload, generation: presetState.generation, engine: get_dev_engine()})});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Unable to save presets.');
        presetState = data;
        selectedPreset = engine_presets().find(p => p.id === selectedPreset?.id) || null;
        if (payload.action === 'save') selectedPreset = engine_presets().find(p => p.scope === payload.scope && p.name === payload.name);
        render_presets();
        document.getElementById('preset-message').textContent = '';
        dialog.close();
    } catch (error) {
        dialog.querySelector('.preset-error').textContent = error instanceof SyntaxError ? 'Unable to save. Reload the page and try again.' : error.message;
    } finally { presetBusy = false; submit.disabled = false; }
}

function initialize_presets(kind) {
    presetKind = kind;
    const form = document.getElementById('workload-form');
    for (const event of ['input', 'change']) form.addEventListener(event, e => {
        if (!e.target.name) return;
        document.getElementById('preset-message').replaceChildren();
        editedFields.add(e.target.name);
        for (const group of presetGroups) if (group.includes(e.target.name)) for (const field of group) editedFields.add(field);
    }, true);
    const save = document.getElementById('preset-save-dialog');
    const manage = document.getElementById('preset-manage-dialog');
    document.getElementById('preset-save-open').onclick = () => {
        document.getElementById('preset-message').replaceChildren();
        preset_scopes(document.getElementById('preset-save-scope'));
        save_slots();
        save.querySelector('.preset-error').textContent = '';
        save.showModal();
        document.getElementById('preset-save-name').focus();
    };
    document.getElementById('preset-save-scope').onchange = save_slots;
    document.getElementById('preset-save-slot').onchange = save_slot_name;
    document.getElementById('preset-save-form').onsubmit = e => {
        e.preventDefault();
        save_presets(save, {action: 'save', scope: document.getElementById('preset-save-scope').value,
            id: document.getElementById('preset-save-slot').value, name: document.getElementById('preset-save-name').value.trim(), settings: capture_preset()});
    };
    const manageScope = document.getElementById('preset-manage-scope');
    manageScope.onchange = () => {
        presetDraft = engine_presets().filter(p => p.scope === manageScope.value && p.editable).map(p => ({id: p.id, name: p.name}));
        render_preset_editor();
    };
    document.getElementById('preset-manage-open').onclick = () => {
        document.getElementById('preset-message').replaceChildren();
        preset_scopes(manageScope);
        manageScope.onchange();
        manage.querySelector('.preset-error').textContent = '';
        manage.showModal();
    };
    document.getElementById('preset-manage-form').onsubmit = e => {
        e.preventDefault();
        save_presets(manage, {action: 'manage', scope: manageScope.value, presets: presetDraft});
    };
    for (const dialog of [save, manage]) {
        dialog.querySelector('[data-close-dialog]').onclick = () => { if (!presetBusy) dialog.close(); };
        dialog.oncancel = e => { if (presetBusy) e.preventDefault(); };
    }
}
