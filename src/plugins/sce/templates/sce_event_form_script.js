{% set field_ids = [
    'age-category-base-date',
    'age-categories',
    'age-category-change-month'
] + ([] if has_multi_tournament_players else ['allow-multi-tournament-players']) %}

var sceTooltipByFieldId = {};
$('#{{ plugin.form_key }}').change(function () {
    if (this.checked) {
        const message = `{{ _('This field is controlled from Sharly-Chess.com.') }}`
        {% for id in field_ids %}
            var inputContainer = document.getElementById('{{ id }}-input-container');
            sceTooltipByFieldId['{{ id }}'] = new bootstrap.Tooltip(inputContainer, {
                title: message,
                placement: 'top',
            });
            $('#{{ id }}').prop('disabled', true);
            $('#{{ id }}-hidden').prop('disabled', false);
        {% endfor %}
        $('#age-category-sets-container').hide();
    } else {
        {% for id in field_ids %}
            if ('{{ id }}' in sceTooltipByFieldId) {
                sceTooltipByFieldId['{{ id }}'].dispose();
                delete sceTooltipByFieldId['{{ id }}'];
            }
            $('#{{ id }}').prop('disabled', false);
            $('#{{ id }}-hidden').prop('disabled', true);
        {% endfor %}
        if($('#plugin_ffe').is(':checked')) {
            $('#plugin_ffe').trigger('change', [false]);
        }
    }
    $('#age-category-sets-configure-button').prop('disabled', this.checked);
});
