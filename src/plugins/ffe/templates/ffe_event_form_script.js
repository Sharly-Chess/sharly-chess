var ratingTypeTooltip = null;
var changeMonthTooltip = null;
var previousFfeEnabled = null;
$('#{{ plugin.form_key }}').change(function () {
    if (this.checked) {
        $('#player-rating-type,#player-rating-type-hidden').val('3').trigger('change');
        const ratingTypeContainer = document.getElementById('player-rating-type-input-container');
        ratingTypeTooltip = new bootstrap.Tooltip(ratingTypeContainer, {
            title: `{{ _('The FFE always uses the FIDE rating when available.') }}`,
            placement: 'top',
        });

        $('#age-category-change-month,#age-category-change-month-hidden').val('9').trigger('change');
        const changeMonthContainer = document.getElementById('age-category-change-month-input-container');
        changeMonthTooltip = new bootstrap.Tooltip(changeMonthContainer, {
            title: `{{ _('The FFE sporting season starts in September.') }}`,
            placement: 'top',
        });
    } else {
        if (ratingTypeTooltip) {
            ratingTypeTooltip.dispose();
            ratingTypeTooltip = null;
        }
        if (changeMonthTooltip) {
            changeMonthTooltip.dispose();
            changeMonthTooltip = null;
        }
        if (previousFfeEnabled) {
            $('#age-category-change-month').val('1').trigger('change');
        }
    }
    previousFfeEnabled = this.checked;
    $('#player-rating-type').prop('disabled', this.checked);
    $('#player-rating-type-hidden').prop('disabled', !this.checked);
    $('#age-category-change-month').prop('disabled', this.checked);
    $('#age-category-change-month-hidden').prop('disabled', !this.checked);

    if (!this.checked && $('#plugin_sce').is(':checked')) {
        $('#plugin_sce').trigger('change', [false]);
    }
});
