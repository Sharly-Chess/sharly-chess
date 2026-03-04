var resultList = [];
var selectedIndex;
var inputField = $("#search-input");

function handleInitialQuery(event) {
    resultList = $('#search-results>li.btn');
    selectedIndex = 0;
    inputField.data("selectedIndex", selectedIndex);

    document.getElementById("player-modal").onkeydown = function(event) {
        if (event.code === "ArrowUp") {
            selectedIndex = Math.max(selectedIndex - 1, 0);
            refreshStyle(resultList, selectedIndex);
            inputField.data("selectedIndex", selectedIndex);
            return false;
        } else if (event.code === "ArrowDown") {
            selectedIndex = Math.min(selectedIndex + 1, resultList.length - 1);
            refreshStyle(resultList, selectedIndex);
            inputField.data("selectedIndex", selectedIndex);
            return false;
        } else if (event.key === "Enter") {
            if (resultList[selectedIndex]) {
                resultList[selectedIndex].click();
            }
            return false;
        }
    };

    refreshStyle(resultList, selectedIndex);
}

function handleListExtension(event) {
    event.target.remove();

    resultList = $('#search-results>li.btn');
    selectedIndex = inputField.data("selectedIndex") || 0;

    refreshStyle(resultList, selectedIndex);
}


function refreshStyle(resultList, selectedIndex) {
    resultList.removeClass("selected-result");
    if (resultList[selectedIndex]) {
        resultList[selectedIndex].scrollIntoView({"block": "center"});
        $(resultList[selectedIndex]).addClass("selected-result");
    }
}