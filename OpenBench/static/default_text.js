function enforce_default_text(id, text) {

    window.addEventListener('DOMContentLoaded', function() {

        var field = document.getElementById(id);

        if (!field)
            return;

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