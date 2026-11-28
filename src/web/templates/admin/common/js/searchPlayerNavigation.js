var resultList = [];
var selectedIndex;

function handleInitialQuery(event) {
    resultList = $('#search-results>li.btn, #search-results>li.bulk-add-result');
    // A list of players to tick stays clear until the arrows are used: its
    // first row is no likelier choice than the others
    selectedIndex = $('#search-results').hasClass('bulk-add-results') ? -1 : 0;

    let searchInput = document.getElementById("search-input");
    let eventListeners = $._data(searchInput, "events")
    if (!eventListeners || !eventListeners.keydown) { // avoid duplicate eventListeners
        $(searchInput).on("keydown", function(event) {
            if (event.code === "ArrowUp") {
                selectedIndex = Math.max(selectedIndex - 1, 0);
                refreshStyle(resultList, selectedIndex);
                return false;
            } else if (event.code === "ArrowDown") {
                selectedIndex = Math.min(selectedIndex + 1, resultList.length - 1);
                refreshStyle(resultList, selectedIndex);
                return false;
            } else if (event.key === "Enter") {
                if (resultList[selectedIndex]) {
                    resultList[selectedIndex].click();
                    return false;
                }
            }
        });
    }

    refreshStyle(resultList, selectedIndex);
}

function handleListExtension(event) {
    event.target.remove();

    let hadResults = resultList.length > 0;
    resultList = $('#search-results>li.btn, #search-results>li.bulk-add-result');
    if (!hadResults) {
        refreshStyle(resultList, selectedIndex);
        return;
    }

    let element = resultList[selectedIndex];
    if (!element) return;
    let parent = element.parentElement;

    let elementPosition = element.getBoundingClientRect();
    let parentPosition = parent.getBoundingClientRect();

    if (elementPosition.top > (parentPosition.top + parentPosition.bottom)/2 ) {
        refreshStyle(resultList, selectedIndex);
    }

}


function refreshStyle(resultList, selectedIndex) {
    resultList.removeClass("selected-result");
    if (resultList[selectedIndex]) {
        resultList[selectedIndex].scrollIntoView(
            {"block": "nearest", "behavior": "smooth"}
        );
        $(resultList[selectedIndex]).addClass("selected-result");
    }
}
