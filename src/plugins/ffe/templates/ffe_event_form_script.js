var ratingTypeTooltip = null;
var changeMonthTooltip = null;
var previousFfeEnabled = null;
$('#{{ plugin.form_key }}').change(function () {
    if (this.checked) {
        // The FFE ranks on the FIDE rating, then on the national one
        $('#rating-preference,#rating-preference-hidden').val('3').trigger('change');
        const ratingTypeContainer = document.getElementById('rating-preference-input-container');
        if (ratingTypeContainer) {
            ratingTypeTooltip = new bootstrap.Tooltip(ratingTypeContainer, {
                title: `{{ _('The FFE always uses the FIDE rating when available.') }}`,
                placement: 'top',
            });
        }

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
    $('#rating-preference').prop('disabled', this.checked);
    $('#rating-preference-hidden').prop('disabled', !this.checked);
    $('#age-category-change-month').prop('disabled', this.checked);
    $('#age-category-change-month-hidden').prop('disabled', !this.checked);

    if (!this.checked && $('#plugin_sce').is(':checked')) {
        $('#plugin_sce').trigger('change', [false]);
    }
});
