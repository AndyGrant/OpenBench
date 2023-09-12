
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

function create_testmode_buttons(engine) {

    // Clear out all of the existing buttons
    var button_div = document.getElementById('test-mode-buttons');
    while (button_div.hasChildNodes())
        button_div.removeChild(button_div.lastChild);

    var index = 0;
    for (let mode in config.engines[engine].testmodes) {

        // Create a new button for the test mode
        var btn       = document.createElement('button')
        btn.innerHTML = mode;
        btn.onclick   = function() { set_test_mode(mode); };

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


function extract_mode_config(mode_str, target) {

    // Find test mode configuration for either Dev or Base

    var selection = document.getElementById(target + '_engine');
    var engine    = selection.options[selection.selectedIndex].value;

    return config.engines[engine].testmodes[mode_str];
}


function set_test_type() {

    var selectA = document.getElementById('test_mode');
    var mode    = selectA.options[selectA.selectedIndex].value;

    var selectB = document.getElementById('dev_engine');
    var engine  = selectB.options[selectB.selectedIndex].value;

    if (mode == 'SPRT') {
        document.getElementById('test_bounds'    ).value = config.engines[engine].bounds
        document.getElementById('test_confidence').value = config.tests.confidence;
        document.getElementById('test_max_games' ).value = 'N/A';
    }

    if (mode == 'GAMES') {
        document.getElementById('test_bounds'    ).value = 'N/A';
        document.getElementById('test_confidence').value = 'N/A';
        document.getElementById('test_max_games' ).value = config.tests.max_games;
    }
}

function set_engine_options(mode_str, target) {

    // Extract UCI options for both the Dev and Base engines
    var dev_options  = extract_mode_config(mode_str, 'dev' )['options'] || 'Threads=1 Hash=8';
    var base_options = extract_mode_config(mode_str, 'base')['options'] || 'Threads=1 Hash=8';

    // Simple case, where we are not updating a base that is cross-engine
    if (target == 'dev' || dev_options == base_options)
        document.getElementById(target + '_options').value = dev_options;

    else {

        // Use the Threads= and Hash= from the dev options, but then make
        // sure to include any specific options that appear in dev options

        var regex   = /(Threads=\d+)\s(Hash=\d+)/;
        var matches = dev_options.match(regex);

        var standard_options = matches[1] + ' ' + matches[2];
        var specific_options = base_options.replace(regex, '');
        var combined_options = standard_options.trim() + ' ' + specific_options.trim();

        document.getElementById('base_options').value = combined_options.trim();
    }
}

function set_test_mode(mode_str) {

    const selection = document.getElementById('dev_engine');
    const engine    = selection.options[selection.selectedIndex].value;
    const mode      = extract_mode_config(mode_str, 'dev');

    document.getElementById('report_rate'  ).value = mode['report_rate']   || 8;
    document.getElementById('workload_size').value = mode['workload_size'] || 32;
    document.getElementById('book_name'    ).value = mode['book']          || config.engines[engine].book;

    document.getElementById('dev_time_control' ).value = mode['timecontrol'] || '10.0+0.1';
    document.getElementById('base_time_control').value = mode['timecontrol'] || '10.0+0.1';

    set_engine_options(mode_str, 'dev');
    set_engine_options(mode_str, 'base');

    if (mode['bounds'] != null) {
        document.getElementById('test_mode').value = 'SPRT'; set_test_type();
        document.getElementById('test_bounds').value = mode['bounds'];
    }

    if (mode['games'] != null) {
        document.getElementById('test_mode').value = 'GAMES'; set_test_type();
        document.getElementById('test_max_games').value = mode['games'];
    }

    if (mode['bounds'] == null && mode['games'] == null) {
        document.getElementById('test_mode').value = 'SPRT'; set_test_type();
    }
}

function set_engine(engine, target) {

    // Always update the Engine and Repository to the defaults
    document.getElementById(target + '_engine').value = engine;
    document.getElementById(target + '_repo'  ).value = repos[engine] || config.engines[engine].source

    // Create dropdown of all Networks associated with the engine
    create_network_options(target + '_network', engine);

    // Set default UCI options as if we were running an STC when changing
    set_engine_options('STC', target);

    if (target == 'dev') {

        // Dev engine decides the Adjudication and Book settings
        document.getElementById('book_name'  ).value = config.engines[engine].book;
        document.getElementById('win_adj'    ).value = config.engines[engine].win_adj;
        document.getElementById('draw_adj'   ).value = config.engines[engine].draw_adj;

        // When swapping the dev engine, redo buttons, base, and test mode
        create_testmode_buttons(engine);
        set_engine(engine, 'base');
        set_test_mode('STC');
    }

    // Default the base engine to it's own base branch
    else document.getElementById(target + '_branch').value = config.engines[engine].base;
}


function enforce_default_text(id, text) {

    window.addEventListener('DOMContentLoaded', function() {

        var field = document.getElementById(id);

        field.addEventListener('input', function() {

            if (field.value.startsWith(text) || field.value === text)
                return;

            if (field.value.endsWith('/'))
                field.value = text + field.value.substr(text.length).replace(/\/+$/, '');
            else
                field.value = text + field.value.substr(text.length);
        });
    });
}