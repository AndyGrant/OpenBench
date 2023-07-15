
var Networks = JSON.parse(document.getElementById('json-networks').textContent);

var Network_Sorting;

function swap_networks(index1, index2) {

    var temp = Networks[index1];
    Networks[index1] = Networks[index2];
    Networks[index2] = temp;

    var table = document.getElementById("network-table");
    var temp_row = table.rows[index1+1].innerHTML
    table.rows[index1+1].innerHTML = table.rows[index2+1].innerHTML;
    table.rows[index2+1].innerHTML = temp_row;
}

function invert_networks() {
    for (let i = 0; Networks.length > i * 2; i++)
        swap_networks(i, Networks.length-i-1);
}

function sort_networks(field) {

    console.log(field);

    if (Network_Sorting == field)
        return invert_networks();

    for (let i = 0; i != Networks.length; i++)
        for (let j = i + 1; j != Networks.length; j++)
            if (Networks[j][field] > Networks[i][field])
                swap_networks(i, j);

    Network_Sorting = field;
};
