/* https://htmx.org/examples/sortable/ */
htmx.onLoad(function(content) {
    var sortables = content.querySelectorAll(".sortable");
    for (var i = 0; i < sortables.length; i++) {
        var sortable = sortables[i];

        options = {
            animation: 150,
            ghostClass: 'blue-background-class',
            // Make the `.htmx-indicator` unsortable
            filter: ".htmx-indicator, .non-sortable",
            onMove: function (evt) {
                // Allow for a fixed first item
                if (evt.related.className.indexOf('non-sortable') !== -1) return 1;

                var dragged = evt.dragged;  // the row being dragged
                var over = evt.related;     // the row we're hovering over
                if (!over) return true;     // allow if nothing to compare

                const a = dragged.dataset.group;
                const b = over.dataset.group;

                if (a !== undefined || b !== undefined) {
                    // If items have a data-group, only allow ordering between them
                    return a === b;
                }

                return evt.related.className.indexOf('htmx-indicator') === -1;
            },
            // Disable sorting on the `end` event
            onEnd: function (evt) {
                this.option("disabled", true);
            },
        };

        // Determine if we need handle-based dragging
        var useHandles = sortable.classList.contains("with-handles");
        if (useHandles) {
            options.handle = ".handle";
        }

        var sortableInstance = new Sortable(sortable, options);

        // Re-enable sorting on the `htmx:afterSwap` event
        sortable.addEventListener("htmx:afterSwap", function() {
            sortableInstance.option("disabled", false);
        });
    }
})
