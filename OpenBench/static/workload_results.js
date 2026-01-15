
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

function fetch_results(workload_id) {
    fetch(`/api/workload/${workload_id}/results/`)
        .then(r => r.json())
        .then(data => populate_results(data.results))
}