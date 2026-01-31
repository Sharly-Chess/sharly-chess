$('#ffe-licence-number').val('{{ player.plugin_data.ffe.ffe_licence_number or '' }}');
$('#ffe-arbiter-title').val('{{ player.plugin_data.ffe.ffe_arbiter_title or '' }}');
$('#ffe-arbiter-title').trigger('change');
