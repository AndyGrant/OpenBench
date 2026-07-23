function copy_text(text) {

    var area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();

    try {
        document.execCommand("copy");
        document.body.removeChild(area);
    }

    catch (err) {
        document.body.removeChild(area);
        console.error("Unable to copy to Clipboard");
    }
}

function copy_text_from_element(element_id, keep_url) {

    var text = document.getElementById(element_id).innerHTML;
    text = text.replace(/<br>/g, "\n");

    if (keep_url)
        text += "\n" + window.location.href;

    copy_text(text);
}


function populate_results(results) {

    const container = document.getElementById('results-container');

    container.innerHTML = ''; // Clear everything for sanity

    results.forEach(result => {
        const tr = document.createElement('tr');

        // Highlight active rows
        if (result.active) tr.classList.add('active-highlight');

        // Collapse the trinomial won/lost/drawn into the pentanomial tuple and
        // its pair count, mirroring the aggregate summary tables above
        const penta = [result.LL, result.LD, result.DD, result.DW, result.WW];
        const pairs = penta.reduce((a, b) => a + b, 0);

        tr.innerHTML = `
            <td><a href="/machines/${result.machine__id}">${result.machine__id}</a></td>
            <td>${result.machine__user__username.charAt(0).toUpperCase() + result.machine__user__username.slice(1)}</td>
            <td class="numeric">${result.games}</td>
            <td>(${penta.join(', ')})</td>
            <td class="numeric">${pairs}</td>
            <td class="numeric">${result.timeloss}</td>
            <td class="numeric">${result.crashes}</td>
        `;

        container.appendChild(tr);
    });
}

async function fetch_results(workload_id) {
    fetch(`/api/workload/${workload_id}/results/`)
        .then(r => r.json())
        .then(data => populate_results(data.results))
}


function summary_cell(tag, text, class_name) {

    // Keys are free-form (cpu names, isa names), so set everything as text to
    // avoid injecting any markup a Machine might have reported
    const cell = document.createElement(tag);
    cell.textContent = text;
    if (class_name) cell.className = class_name;
    return cell;
}

function append_summary_section(table, label, rows) {

    // A header row naming the grouping, then one tbody of data rows. All three
    // sections share the one table, so their columns line up automatically.
    const header = document.createElement('tr');
    header.className = 'table-header';
    header.appendChild(summary_cell('th', label));

    ['Penta', 'Elo', 'Pairs', '%'].forEach(name => {
        header.appendChild(summary_cell('th', name));
    });

    table.appendChild(header);

    const tbody = document.createElement('tbody');

    rows.forEach(row => {
        const tr = document.createElement('tr');

        // The API hands us display-ready fields: the penta tuple as a string,
        // a point-estimate Elo, the pair count, and the % of the group total
        tr.appendChild(summary_cell('td', row.key));
        tr.appendChild(summary_cell('td', row.penta));
        tr.appendChild(summary_cell('td', row.elo,   'numeric'));
        tr.appendChild(summary_cell('td', row.pairs, 'numeric'));
        tr.appendChild(summary_cell('td', row.percent, 'numeric'));

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
}

async function fetch_summary(workload_id) {
    fetch(`/api/workload/${workload_id}/summary/`)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('summary-container');
            container.innerHTML = ''; // Rebuild the whole table each fetch

            const table = document.createElement('table');
            table.className = 'stripes wrappable';

            append_summary_section(table, 'User', data.summary.user);
            append_summary_section(table, 'CPU',  data.summary.cpu_name);
            append_summary_section(table, 'ISA',  data.summary.isa_name);

            container.appendChild(table);
        })
}


async function copy_spsa_inputs(workload_id) {
    const resp = await fetch(`/api/spsa/${workload_id}/inputs/`)
    const text = await resp.text()
    copy_text(text)
}

async function copy_spsa_outputs(workload_id) {
    const resp = await fetch(`/api/spsa/${workload_id}/outputs/`)
    const text = await resp.text()
    copy_text(text)
}

async function fetch_spsa_digest(workload_id) {
    const resp  = await fetch(`/api/spsa/${workload_id}/digest/`)
    const text  = await resp.text()
    const lines = text.trim().split('\n')

    // Skip the header line (index 0) and process data rows
    const tbody = document.getElementById('spsa-digest-body-container')
    tbody.innerHTML = ''

    for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',')
        const tr = document.createElement('tr')

        values.forEach(value => {
            const td = document.createElement('td')
            td.textContent = value
            tr.appendChild(td)
        })

        tbody.appendChild(tr)
    }

    // Show the data and hide the button
    tbody.style.display = ''
    const buttonContainer = document.getElementById('spsa-digest-button-container')
    buttonContainer.style.display = 'none'
}
