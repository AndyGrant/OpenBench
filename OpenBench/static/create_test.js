
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

function create_preset_buttons(engine) {

    // Clear out all of the existing buttons
    var button_div = document.getElementById('test-mode-buttons');
    while (button_div.hasChildNodes())
        button_div.removeChild(button_div.lastChild);

    var index = 0;
    for (let mode in config.engines[engine].test_presets) {

        // Don't include the global defaults
        if (mode == 'default')
            continue;

        // Create a new button for the test mode
        var btn       = document.createElement('button')
        btn.innerHTML = mode;
        btn.onclick   = function() { apply_preset(mode); };

        // Apply all of our CSS bootstrapping
        btn.classList.add('anchorbutton');
        btn.classList.add('btn-preset');
        btn.classList.add('mt-2');
        btn.classList.add('w-100');

        // Put the button in a div, so we can handle padding
        var div = document.createElement('div')
        div.appendChild(btn)
        div.classList.add('col-half');

        // Left pad everything but the first
        if ((index % 4) != 0)
            div.classList.add('pl-1');

        // Right pad everything but the last
        if ((index % 4) != 3)
            div.classList.add('pr-1');

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

function add_defaults_to_preset(engine, preset) {

    // Use both the defaults, and this specific preset's settings
    const default_settings = config.engines[engine].test_presets['default'] || {};
    const preset_settings  = config.engines[engine].test_presets[preset] || {};

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

        if (option_name == 'test_bounds') {
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

function retain_specific_options(engine, preset) {

    // This is not applicable for self-play
    if (get_dev_engine() == get_base_engine())
        return;

    // Extract the Threads and Hash settings from the Dev Options

    const dev_options = document.getElementById('dev_options').value;
    const dev_threads = dev_options.match(/\bThreads\s*=\s*(\d+)\b/)[1];
    const dev_hash    = dev_options.match(/\bHash\s*=\s*(\d+)\b/)[1];

    // From the base options, replace the Threads= and Hash=

    let base_options = add_defaults_to_preset(engine, preset)['base_options']
                    || add_defaults_to_preset(engine, preset)['both_options'];

    base_options = base_options.replace(/\bThreads\s*=\s*\d+\b/g, 'Threads=' + dev_threads);
    base_options = base_options.replace(/\bHash\s*=\s*\d+\b/g, 'Hash=' + dev_hash);

    set_option('base_options', base_options);
}


function apply_preset(preset) {

    // Add the defaults to the preset-specific options
    const settings  = add_defaults_to_preset(get_dev_engine(), preset)

    for (const option in settings) {

        if (!settings.hasOwnProperty(option))
            continue;

        else if (!option.startsWith('both_'))
            set_option(option, settings[option]);

        else {
            set_option(option.replace('both_', 'dev_'), settings[option]);
            set_option(option.replace('both_', 'base_'), settings[option]);
        }
    }

    // For cross-engine, keep the original Hash/Threads, but
    // add any other settings that might be specific to the engine
    retain_specific_options(get_base_engine(), preset);
}

function change_engine(engine, target) {

    // Set the Engine, Repo, and init the Networks dropdown
    set_engine(engine, target);

    // 1. Always set base, when setting the dev engine
    // 2. When changing the dev engine, update the test-mode buttons

    if (target == 'dev') {
        set_engine(engine, 'base');
        create_preset_buttons(engine);
    }

    // Always reinit to STC for clarity to the user
    apply_preset('STC');
}