
{% set field_ids = [
    'date-range',
    'age-category-base-date',
    'age-categories',
    'age-category-change-month'
] %}

var pluginContainer = document.getElementById('{{ plugin.form_key }}-plugin-container');
{% for id in field_ids %}
    {% set name = id|replace('-', '_') %}
    var hiddenInput = document.createElement('input');
    hiddenInput.setAttribute('type', 'hidden');
    hiddenInput.setAttribute('name', '{{ name }}');
    hiddenInput.setAttribute('id', '{{ id }}-sce-hidden');
    hiddenInput.setAttribute('value', `{{ data[field] }}`);
    pluginContainer.appendChild(hiddenInput);
{% endfor %}

var message = ``;
var sceTooltipByFieldId = {};
$('#{{ plugin.form_key }}').change(function () {
    if (this.checked) {
        {% for id in field_ids %}
            var inputContainer = document.getElementById('{{ id }}-input-container');
            sceTooltipByFieldId['{{ id }}'] = new bootstrap.Tooltip(inputContainer, {
                title: `{{ _('This field is controlled from Sharly-Chess.com.') }}`,
                placement: 'top',
            });
            $('#{{ id }}').prop('disabled', true);
            $('#{{ id }}-sce-hidden').prop('disabled', false);
        {% endfor %}
        $('#age-category-sets-container').hide();
    } else {
        {% for id in field_ids %}
            if ('{{ id }}' in sceTooltipByFieldId) {
                sceTooltipByFieldId['{{ id }}'].dispose();
                delete sceTooltipByFieldId['{{ id }}'];
            }
            $('#{{ id }}').prop('disabled', false);
            $('#{{ id }}-sce-hidden').prop('disabled', true);
        {% endfor %}
    }
    $('#age-category-sets-configure-button').prop('disabled', this.checked);
});
