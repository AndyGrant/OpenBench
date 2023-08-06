
var Networks = JSON.parse(document.getElementById('json-networks').textContent);

function is_greater_than(a, b, attrs) {

    for (const attr of attrs) {
        if (a[attr] === b[attr])
            continue;
        return a[attr] > b[attr];
    }

    return false; // Objects are equal
}

function swap_networks(index1, index2) {

    var temp = Networks[index1];
    Networks[index1] = Networks[index2];
    Networks[index2] = temp;

    var table = document.getElementById("network-table");
    var temp_row = table.rows[index1+1].innerHTML
    table.rows[index1+1].innerHTML = table.rows[index2+1].innerHTML;
    table.rows[index2+1].innerHTML = temp_row;
}

function sort_networks(fields) {

    for (let i = 0; i != Networks.length; i++)
        for (let j = i + 1; j != Networks.length; j++)
            if (is_greater_than(Networks[j], Networks[i], fields))
                swap_networks(i, j);
}
