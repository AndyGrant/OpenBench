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

    var options = {
        year   : 'numeric', month  : '2-digit',
        day    : '2-digit', hour   : '2-digit',
        minute : '2-digit', second : '2-digit',
        hour12 : false,
    };

    const formatter = new Intl.DateTimeFormat('en-US', options);

    results.forEach(result => {
        const tr = document.createElement('tr');

        // Highlight active rows
        if (result.active) tr.classList.add('active-highlight');

        const ts        = Number(result.updated)
        const date      = new Date(ts * 1000);
        const formatted = formatter.format(date);

        tr.innerHTML = `
            <td><a href="/machines/${result.machine__id}">${result.machine__id}</a></td>
            <td>${result.machine__user__username.charAt(0).toUpperCase() + result.machine__user__username.slice(1)}</td>
            <td class="">${formatted}</td>
            <td class="numeric">${result.games}</td>
            <td class="numeric">${result.wins}</td>
            <td class="numeric">${result.losses}</td>
            <td class="numeric">${result.draws}</td>
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
