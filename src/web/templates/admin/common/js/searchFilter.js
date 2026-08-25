var filtersInitialized = false;
var filters = {};
var filterRefreshTimer;
var ENABLED_FILTERS_BY_DATASOURCE = {
    "ffe-online": ["federation_filter", "gender_filter", "category_filter", "club_filter", "ffe_licence_filter", "ffe_league_filter"],
    "ffe-local": ["federation_filter", "gender_filter", "club_filter", "ffe_licence_filter", "ffe_league_filter"],
    "fide": ["federation_filter", "gender_filter"]
};
var DISABLED_TITLE = "{{ _('This filter is disabled for the selected data source.') }}";

function filterInit() {
    filtersInitialized = false;
    let filterNames = $.map($("#filter-form select, #filter-form input[type='text']"), (x)=> x.name)
    let storedFilters = JSON.parse(localStorage.getItem("searchFilters")) || {};

    for (let filterName of filterNames) {
        filters[filterName] = storedFilters[filterName];
        if (filters[filterName]) {
            $(`#filter-form [name=${filterName}]`).val(filters[filterName]).trigger("change");
        }
    }
    updateFilterCount();

    let dataSource = $("#data-source-select").val();
    let enabledFilters = ENABLED_FILTERS_BY_DATASOURCE[dataSource];
    $("#filter-form select, #filter-form input[type='text']").prop('disabled', true);
    $("div[id*=filter-wrapper]").attr("title", DISABLED_TITLE);

    for (let filter of enabledFilters) {
        $(`#filter-form [name="${filter}"]`).prop('disabled', false);
        $(`#filter-form [name="${filter}"]`).closest("div[id*=filter-wrapper]").removeAttr("title");
    }

    filtersInitialized = true;
}

function delayFilterChange(elem, delay=400) {
    if (filterRefreshTimer) {clearTimeout(filterRefreshTimer);}
    filterRefreshTimer = setTimeout(() => {
        onFilterChange(elem);
    }, delay);
}

function onFilterChange(elem) { // save filters into browser storage and refresh UI
    if (!filtersInitialized){return}
    filters[elem.name] = $(elem).val();
    $('#search-input')[0].dispatchEvent(new CustomEvent('filter_change', {bubbles: true, cancelable: true}));
    localStorage.setItem("searchFilters", JSON.stringify(filters));
    updateFilterCount();
}

function updateFilterCount() { // update the badge

    let filterCount = Object.keys(filters).reduce(function (c, x) {
        let filterElem = $(`#filter-form [name='${x}']`);
        let isFilterActive = Boolean(filterElem.val().length) * !filterElem.prop("disabled");
        return c + isFilterActive;
    }, 0);

    if (filterCount >= 1) {
        $("#filter-count").html(filterCount);
        $("#filter-count").addClass("button_badge");
    } else {
        $("#filter-count").html("");
        $("#filter-count").removeClass("button_badge");
    }
}

function getFilters() { // return only filters with a value
    let f = {};
    for (let key of Object.keys(filters)) {
        if (filters[key] && filters[key].length) {
            f[key] = filters[key];
        }
    }
    return JSON.stringify(f);
}
