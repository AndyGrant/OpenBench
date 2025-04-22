
function copy_text(element_id, keep_url, code_blocks=false) {

    var text = document.getElementById(element_id).innerHTML;
    text = text.replace(/<br>/g, "\n");

    if (code_blocks)
        text = "```\n" + text + "\n```";

    if (keep_url)
        text += "\n" + window.location.href;

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