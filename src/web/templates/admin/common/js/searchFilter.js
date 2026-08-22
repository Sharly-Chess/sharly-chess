var filters = {};
var filtersInitialized = false;
var filterRefreshTimer;

function init() {
    filtersInitialized = false;
    let filterNames = $.map($("#filter-form select,input"), (x)=> x.name)
    let storedFilters = JSON.parse(localStorage.getItem("searchFilters")) || {};

    for (let filterName of filterNames) {
        filters[filterName] = storedFilters[filterName];
        if (filters[filterName]) {
            $(`#filter-form [name=${filterName}]`).val(filters[filterName]).trigger("change");
        }
    }
    updateFilterCount();
    filtersInitialized = true;
}

function delayFilterChange(elem, delay=400) {
    if (filterRefreshTimer) {clearTimeout(filterRefreshTimer);}
    filterRefreshTimer = setTimeout(() => {
        onFilterChange(elem);
    }, delay);
}

function onFilterChange(elem) {
    if (!filtersInitialized){return}
    filters[elem.name] = $(elem).val();
    if (filters[elem.name] == "__placeholder__") {filters[elem.name] = "";}
    $('#search-input')[0].dispatchEvent(new CustomEvent('filter_change', {bubbles: true, cancelable: true}));
    localStorage.setItem("searchFilters", JSON.stringify(filters));
    updateFilterCount();
}

function updateFilterCount() {
    let filterCount = Object.values(filters).reduce((c, x) => c + Boolean(x && x.length), 0);

    if (filterCount >= 1) {
        $("#filter-count").html(filterCount);
        $("#filter-count").addClass("button_badge");
    } else {
        $("#filter-count").html("");
        $("#filter-count").removeClass("button_badge");
    }
}

function getFilters() {
    let f = {};
    for (let key of Object.keys(filters)) {
        if (filters[key] && filters[key].length) {
            f[key] = filters[key];
        }
    }
    return JSON.stringify(f);
}

init();
