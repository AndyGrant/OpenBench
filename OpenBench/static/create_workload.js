
var config   = JSON.parse(document.getElementById('json-config'  ).textContent);
var networks = JSON.parse(document.getElementById('json-networks').textContent);
var repos    = JSON.parse(document.getElementById('json-repos'   ).textContent);

function create_network_options(field_id, engine) {

    var has_default     = false;
    var network_options = document.getElementById(field_id);

    // Delete all existing Networks
    while (network_options.length)
        network_options.remove(0);

    // Add each Network that matches the given engine
    for (const network of networks) {

        if (network.engine !== engine)
            continue;

        var opt      = document.createElement('option');
        opt.text     = network.name;
        opt.value    = network.sha256;
        opt.selected = network.default;
        network_options.add(opt)

        has_default = has_default || network.default;
    }

    { // Add a None option and set it to default if there was not one yet
        var opt       = document.createElement('option');
        opt.text      = 'None';
        opt.value     = '';
        opt.selected  = !has_default;
        network_options.add(opt);
    }
}

function create_preset_buttons(engine, workload_type) {

    // Clear out all of the existing buttons
    var button_div = document.getElementById('test-mode-buttons');
    while (button_div.hasChildNodes())
        button_div.removeChild(button_div.lastChild);

    const presets = workload_type == 'TEST'    ? config.engines[engine].test_presets
                  : workload_type == 'TUNE'    ? config.engines[engine].tune_presets
                  : workload_type == 'DATAGEN' ? config.engines[engine].datagen_presets : {};

    var index = 0;
    for (let mode in presets) {

        // Don't include the global defaults
        if (mode == 'default')
            continue;

        // Create a new button for the test mode
        var btn       = document.createElement('button')
        btn.innerHTML = mode;
        btn.onclick   = function() { apply_preset(mode, workload_type); };

        // Apply all of our CSS bootstrapping
        btn.classList.add('anchorbutton');
        btn.classList.add('btn-preset');
        btn.classList.add('mt-1');
        btn.classList.add('w-100');

        // Put the button in a div, so we can handle padding
        var div = document.createElement('div')
        div.appendChild(btn)
        div.classList.add('col-half');

        // Left pad everything but the first
        if ((index % 4) != 0)
            div.classList.add('pl-half');

        // Right pad everything but the last
        if ((index % 4) != 3)
            div.classList.add('pr-half');

        button_div.append(div);
        index++;
    }
}


function get_dev_engine() {
    const selection = document.getElementById('dev_engine');
    return selection.options[selection.selectedIndex].value;
}

function get_base_engine() {
    const selection = document.getElementById('base_engine');
    return selection.options[selection.selectedIndex].value;
}

function get_presets(engine, preset, workload_type) {
    return workload_type == 'TEST'    ? config.engines[engine].test_presets[preset]
         : workload_type == 'TUNE'    ? config.engines[engine].tune_presets[preset]
         : workload_type == 'DATAGEN' ? config.engines[engine].datagen_presets[preset] : {};
}


function add_defaults_to_preset(engine, preset, workload_type) {

    const default_settings = get_presets(engine, 'default', workload_type);
    const preset_settings  = get_presets(engine, preset, workload_type);

    let settings = {}

    for (const key in default_settings)
        settings[key] = default_settings[key];

    for (const key in preset_settings)
        settings[key] = preset_settings[key];

    return settings;
}

function set_engine(engine, target) {

    document.getElementById(target + '_engine').value = engine;
    document.getElementById(target + '_repo'  ).value = repos[engine] || config.engines[engine].source

    create_network_options(target + '_network', engine);
}

function set_option(option_name, option_value) {

    const element = document.getElementById(option_name);

    if (element == null)
        console.log(option_name + ' was not found.');

    else if (element.tagName.toLowerCase() != 'select') {

        element.value = option_value;

        if (option_name == 'test_max_games') {
            document.getElementById('test_mode').value = "GAMES";
            document.getElementById('test_bounds').value = 'N/A';
            document.getElementById('test_confidence').value = 'N/A';
        }

        if (option_name == 'test_bounds' || option_name == 'test_confidence') {
            document.getElementById('test_mode').value = "SPRT";
            document.getElementById('test_max_games').value = 'N/A';
        }
    }

    else {
        for (let i = 0; i < element.options.length; i++)
            if (element.options[i].text === option_value || element.options[i].value === option_value)
                element.value = element.options[i].value;
    }
}

function retain_specific_options(engine, preset, workload_type) {

    // This is not applicable for self-play
    if (get_dev_engine() == get_base_engine())
        return;

    // Extract the Threads and Hash settings from the Dev Options

    const dev_options   = document.getElementById('dev_options').value;

    const threads_match = dev_options.match(/\bThreads\s*=\s*(\d+)\b/);
    const hash_match    = dev_options.match(/\bHash\s*=\s*(\d+)\b/);

    const dev_threads   = threads_match ? threads_match[1] : null;
    const dev_hash      = hash_match    ? hash_match[1]    : null;

    // From the base options, replace the Threads= and Hash=

    const settings = add_defaults_to_preset(engine, preset, workload_type);

    let base_options = settings['base_options'] || settings['both_options'];

    base_options = base_options.replace(/\bThreads\s*=\s*\d+\b/g, 'Threads=' + dev_threads);
    base_options = base_options.replace(/\bHash\s*=\s*\d+\b/g, 'Hash=' + dev_hash);

    set_option('base_options', base_options);

    // Retain the base engine's original base_branch, instead of leeting the dev engine override

    if (settings.hasOwnProperty('base_branch'))
        set_option('base_branch', settings['base_branch']);
}


function apply_preset(preset, workload_type) {

    if (preset != 'default')
        apply_preset('default', workload_type);

    const settings = get_presets(get_dev_engine(), preset, workload_type);

    for (const option in settings) {

        if (!settings.hasOwnProperty(option))
            continue;

        else if (!option.startsWith('both_'))
            set_option(option, settings[option]);

        else {
            set_option(option.replace('both_', 'dev_'), settings[option]);

            if (workload_type == 'TEST' || workload_type == "DATAGEN")
                set_option(option.replace('both_', 'base_'), settings[option]);
        }
    }

    // For cross-engine tests, keep the original Hash/Threads, but
    // add any other settings that might be specific to the engine
    if (workload_type == 'TEST' || workload_type == "DATAGEN") {
        try {
            retain_specific_options(get_base_engine(), preset, workload_type);
        } catch (error) {}
    }
}

function change_engine(engine, target, workload_type) {

    set_engine(engine, target);

    if (target == 'dev')
        create_preset_buttons(engine, workload_type);

    if (target == 'dev' && (workload_type == 'TEST' || workload_type == 'DATAGEN'))
        set_engine(engine, 'base');

    apply_preset('STC', workload_type);
}

function set_test_type() {

    // When swapping from SPRT -> FIXED, we disable test_bounds and test_confidence
    // When swapping from FIXED -> SPRT, we disable test_max_games
    //
    // Attempt to fill SPRT fields using default settings, then STC settings.
    // Attempt to fill FIXED fields using default settings, then just use 40,000

    var selectA  = document.getElementById('test_mode');
    var mode     = selectA.options[selectA.selectedIndex].value;

    var selectB  = document.getElementById('dev_engine');
    var engine   = selectB.options[selectB.selectedIndex].value;

    var base = get_presets(engine, 'default', 'TEST');
    var stc  = get_presets(engine, 'STC', 'TEST');

    if (!stc) // If there are no STC settings, re-use the defaults
        stc = base;

    if (mode == 'SPRT') {
        document.getElementById('test_bounds'    ).value = base.test_bounds || stc.test_bounds;
        document.getElementById('test_confidence').value = base.test_confidence || stc.test_confidence;
        document.getElementById('test_max_games' ).value = 'N/A';
    }

    if (mode == 'GAMES') {
        document.getElementById('test_bounds'    ).value = 'N/A';
        document.getElementById('test_confidence').value = 'N/A';
        document.getElementById('test_max_games' ).value = base.test_max_games || stc.test_max_games || 40000;
    }
}
