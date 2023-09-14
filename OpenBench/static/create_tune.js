
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
    for (let mode in config.engines[engine].tunemodes) {

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

function extract_mode_config(mode_str) {

    // Find test mode configuration for the engine
    var selection = document.getElementById('engine');
    var engine    = selection.options[selection.selectedIndex].value;
    return config.engines[engine].tunemodes[mode_str];
}

function set_engine_options(mode_str) {

    // Extract UCI options for both the engine
    var options = extract_mode_config(mode_str)['options'];
    document.getElementById('options').value = options;
}

function set_test_mode(mode_str) {

    const selection = document.getElementById('engine');
    const engine    = selection.options[selection.selectedIndex].value;
    const mode      = extract_mode_config(mode_str);

    document.getElementById('book_name'    ).value = mode['book'] || config.engines[engine].book;
    document.getElementById('time_control' ).value = mode['timecontrol'] || '10.0+0.1';

    set_engine_options(mode_str);
}


/* External */

function set_engine(engine) {

    // Always update the Engine and Repository to the defaults
    document.getElementById('engine').value = engine;
    document.getElementById('repo'  ).value = repos[engine] || config.engines[engine].source

    // Create dropdown of all Networks associated with the engine
    create_network_options('network', engine);

    // Set default UCI options as if we were running an STC when changing
    set_engine_options('STC');

    // Engine decides the Adjudication and Book settings
    document.getElementById('book_name'  ).value = config.engines[engine].book;
    document.getElementById('win_adj'    ).value = config.engines[engine].win_adj;
    document.getElementById('draw_adj'   ).value = config.engines[engine].draw_adj;

    set_test_mode('STC');
    create_testmode_buttons(engine)
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