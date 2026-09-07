
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

function get_dev_engine() {
    const selection = document.getElementById('dev_engine');
    return selection?.value || '';
}

function get_base_engine() {
    const selection = document.getElementById('base_engine');
    return selection?.value || '';
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
        document.getElementById('test_bounds'    ).value = [base.test_bounds, stc.test_bounds].find(value => value && value !== 'N/A') || '[0.00, 2.00]';
        document.getElementById('test_confidence').value = [base.test_confidence, stc.test_confidence].find(value => value && value !== 'N/A') || '[0.05, 0.05]';
        document.getElementById('test_max_games' ).value = 'N/A';
    }

    if (mode == 'GAMES') {
        document.getElementById('test_bounds'    ).value = 'N/A';
        document.getElementById('test_confidence').value = 'N/A';
        document.getElementById('test_max_games' ).value = [base.test_max_games, stc.test_max_games].find(value => value && value !== 'N/A') || 40000;
    }
}
