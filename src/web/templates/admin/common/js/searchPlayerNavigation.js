var resultList = [];
var selectedIndex;

function handleInitialQuery(event) {
    resultList = $('#search-results>li.btn');
    selectedIndex = 0;

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
                }
                event.stopPropagation();
            }
        });
    }

    refreshStyle(resultList, selectedIndex);
}

function handleListExtension(event) {
    event.target.remove();

    resultList = $('#search-results>li.btn');
    
    let element = resultList[selectedIndex];
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
        resultList[selectedIndex].scrollIntoView({"block": "center"});
        $(resultList[selectedIndex]).addClass("selected-result");
    }
}