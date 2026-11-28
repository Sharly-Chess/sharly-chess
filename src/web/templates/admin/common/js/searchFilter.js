var filtersInitialized = false;
var filters = {};
var filterRefreshTimer;
var ENABLED_FILTERS_BY_DATASOURCE = {{ enabled_filters_by_datasource|tojson }};
var FILTERS_BY_TOURNAMENT = {{ filters_by_tournament|tojson }};
// Where the filters are remembered, and what they are before ever being set
var SEARCH_FILTERS_KEY = {{ (search_filters_key or 'searchFilters')|tojson }};
var DEFAULT_SEARCH_FILTERS = {{ (default_search_filters or {})|tojson }};
var enabledFilters;


function filterInit() {
    filtersInitialized = false;
    let filterNames = $.map($("#filter-form select, #filter-form input[type='text']"), (x)=> x.name)
    let stored = localStorage.getItem(SEARCH_FILTERS_KEY);
    let storedFilters = (stored === null ? DEFAULT_SEARCH_FILTERS : JSON.parse(stored)) || {};

    for (let filterName of filterNames) {
        filters[filterName] = storedFilters[filterName];
        $(`#filter-form [name=${filterName}]`).val(filters[filterName]).trigger("change");
    }

    let dataSource = $("#data-source-select").val();
    if (!Object.keys(ENABLED_FILTERS_BY_DATASOURCE).includes(dataSource)) {return;}
    enabledFilters = ENABLED_FILTERS_BY_DATASOURCE[dataSource];
    updateFilterCount();

    $("#filter-form select, #filter-form input[type='text']").closest("div[id*=filter-wrapper]").parent().hide();

    for (let filter of enabledFilters) {
        $(`#filter-form [name="${filter}"]`).closest("div[id*=filter-wrapper]").parent().show();
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
    localStorage.setItem(SEARCH_FILTERS_KEY, JSON.stringify(filters));
    updateFilterCount();
}

function updateFilterCount() { // update the badge

    let filterCount = Object.keys(filters).reduce(function (c, filterName) {
        let filterElem = $(`#filter-form [name='${filterName}']`);
        let isFilterActive = enabledFilters.includes(filterName) && Boolean(filterElem.val().length);
        return c + isFilterActive;
    }, 0);

    $("#filter-count").html(filterCount >= 1 ? filterCount : "");
    $("#filter-count").toggleClass("d-none", filterCount < 1);
}

function loadFiltersFromTournament(tournamentId) {
    filters = {};
    for (let filter of FILTERS_BY_TOURNAMENT[tournamentId]) {
        filters[filter[0]] = filter[1];
    }

    localStorage.setItem(SEARCH_FILTERS_KEY, JSON.stringify(filters));
    filterInit()

}

function clearFilters() {
    localStorage.setItem(SEARCH_FILTERS_KEY, "{}");
    filterInit();
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
