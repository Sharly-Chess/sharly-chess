"""Restricting the height of the list a selection displays.

The list of a selection is as tall as what it holds, which fills the screen when
it holds the federations. macOS makes a menu scrollable when it does not fit the
rectangle its delegate confines it to, and GTK makes a selection display its
items in a scrollable list instead of a menu when it is told to, which is how
the height of the list is restricted here.

This is the approach of the ``max_visible_items`` option added to Toga
(https://github.com/beeware/toga/pull/4691): once the option is released, this
module goes away and the option is passed to the selections instead.
"""

import sys

import toga

if sys.platform == 'darwin':
    from rubicon.objc import objc_method, objc_property

    # From the backend, which is what loads AppKit.
    from toga_cocoa.libs import NSMenu, NSObject, NSPoint, NSRect, NSScreen, NSSize

    #: The height of what a menu displays on top of its items, measured once.
    _menu_chrome_height: float | None = None

    def menu_chrome_height() -> float:
        """The height of the parts of a menu that are not its items. macOS
        exposes neither it nor the height of an item, and both depend on the
        version and on the settings of the user, so they are measured from
        menus holding one and two items."""
        global _menu_chrome_height
        if _menu_chrome_height is None:
            heights = []
            for item_count in (1, 2):
                menu = NSMenu.alloc().init()
                for index in range(item_count):
                    menu.addItemWithTitle(
                        f'item {index}', action=None, keyEquivalent=''
                    )
                heights.append(menu.size.height)
            item_height = heights[1] - heights[0]
            _menu_chrome_height = heights[0] - item_height
        return _menu_chrome_height

    class SelectionMenuDelegate(NSObject):  # type: ignore[misc, valid-type]
        button = objc_property(object, weak=True)
        max_visible_items = objc_property(object)

        @objc_method
        def confinementRectForMenu_onScreen_(self, menu, screen) -> NSRect:
            """The region the list is displayed in. A zero rectangle leaves it
            to macOS, which uses the whole screen."""
            no_confinement = NSRect(NSPoint(0, 0), NSSize(0, 0))
            max_visible_items = self.max_visible_items
            button = self.button
            if (
                max_visible_items is None
                or button is None
                or button.window is None
                or menu.numberOfItems <= max_visible_items
            ):
                return no_confinement
            if screen is None:
                screen = NSScreen.mainScreen
            if screen is None:
                return no_confinement

            # The height of an item comes from the menu itself, so that whatever
            # the items carry is taken into account.
            chrome = menu_chrome_height()
            item_height = (menu.size.height - chrome) / menu.numberOfItems
            height = chrome + item_height * max_visible_items

            # A list that would not fit the screen anyway is left to macOS,
            # which makes it scrollable and handles the edges of the screen.
            visible_frame = screen.visibleFrame
            if height >= visible_frame.size.height:
                return no_confinement

            # The list drops down from the top of the selection and can not be
            # displayed outside the rectangle, which is therefore a band of the
            # screen starting *height* below the top of the selection, and
            # covering it (a band that does not would display no list at all).
            button_frame = button.window.convertRectToScreen(
                button.convertRect(button.bounds, toView=None)
            )
            button_top = button_frame.origin.y + button_frame.size.height
            origin_y = max(visible_frame.origin.y, button_top - height)
            return NSRect(
                NSPoint(visible_frame.origin.x, origin_y),
                NSSize(
                    visible_frame.size.width,
                    button_top + button_frame.size.height - origin_y,
                ),
            )
elif sys.platform == 'linux':
    from toga_gtk.libs import GLib, GTK_VERSION, Gtk

    #: Makes a selection display its items in a list, which GTK confines to the
    #: screen and scrolls, instead of in a menu, which it does neither to.
    _LIST_APPEARANCE_CSS = b'* { -GtkComboBox-appears-as-list: 1; }'

    def list_parts(combo_box) -> tuple | None:
        """The scrolled window and the tree view the list of *combo_box* is
        displayed in. GTK keeps both private, so they are looked for among the
        toplevel windows, by the items the tree view displays."""
        model = combo_box.get_model()
        for window in Gtk.Window.list_toplevels():
            if not isinstance(window, Gtk.Bin):
                continue
            scrolled_window = window.get_child()
            if not isinstance(scrolled_window, Gtk.ScrolledWindow):
                continue
            tree_view = scrolled_window.get_child()
            if isinstance(tree_view, Gtk.TreeView) and tree_view.get_model() is model:
                return scrolled_window, tree_view
        return None

    def item_height(tree_view) -> float | None:
        """The height of an item of *tree_view*, measured from the height it
        asks for, None as long as it asks for nothing (which it does until its
        items have been laid out once)."""
        item_count = tree_view.get_model().iter_n_children(None)
        if not item_count:
            return None
        natural_height = tree_view.get_preferred_height()[1]
        if not natural_height:
            return None
        return natural_height / item_count

    def restrict_list(combo_box, max_visible_items: int):
        """Gives the scrolled window the height of *max_visible_items* items,
        which GTK sizes and places the list from. Done before GTK measures the
        list, and again before each of the next ones, as the items are only
        measurable once they have been laid out."""
        parts = list_parts(combo_box)
        if parts is None:
            return
        scrolled_window, tree_view = parts
        if tree_view.get_model().iter_n_children(None) <= max_visible_items:
            return
        height = item_height(tree_view)
        if height is None:
            return
        height = round(height * max_visible_items)
        scrolled_window.set_min_content_height(height)
        scrolled_window.set_max_content_height(height)

    def scroll_to_item(tree_view, index: int) -> bool:
        """Displays the item of *tree_view* at *index*, halfway down the list."""
        tree_view.scroll_to_cell(
            Gtk.TreePath.new_from_indices([index]), None, True, 0.5, 0
        )
        return GLib.SOURCE_REMOVE

    def show_selected_item(tree_view, _allocation, combo_box):
        """Scrolls the displayed list to the selected item, which is out of
        sight when it is not among the items a restricted list displays. GTK
        scrolls a list back to its first item each time it lays it out, and it
        only takes a scroll once it has laid the list out for good, which is
        why this is both done on every layout and left for later."""
        scrolled_window = tree_view.get_parent()
        if (
            not combo_box.get_property('popup-shown')
            or scrolled_window.get_min_content_height() <= 0
        ):
            return
        index = combo_box.get_active()
        if index < 0:
            return
        GLib.idle_add(scroll_to_item, tree_view, index)

    def keep_list_scrollable(scrolled_window, _parameter):
        """Keeps the list scrollable, which GTK stops it from being each time it
        displays it, and which is what a restricted list is measured from: a
        list that does not scroll is as tall as everything it holds."""
        horizontal_policy, vertical_policy = scrolled_window.get_policy()
        if (
            vertical_policy == Gtk.PolicyType.NEVER
            and scrolled_window.get_min_content_height() > 0
        ):
            scrolled_window.set_policy(horizontal_policy, Gtk.PolicyType.AUTOMATIC)


def limit_popup_height(selection: toga.Selection, max_visible_items: int):
    """Displays at most *max_visible_items* items in the list of *selection*,
    which is scrolled to reach the others. Platforms whose list is bounded
    already are left alone."""
    if sys.platform == 'darwin':
        button = selection._impl.native
        delegate = SelectionMenuDelegate.alloc().init()
        delegate.button = button
        delegate.max_visible_items = max_visible_items
        # The menu holds its delegate weakly, and the selection is what keeps
        # this one alive.
        selection._menu_delegate = delegate
        button.menu.delegate = delegate
    elif sys.platform == 'linux' and GTK_VERSION < (4, 0, 0):
        combo_box = selection._impl.native
        provider = Gtk.CssProvider()
        provider.load_from_data(_LIST_APPEARANCE_CSS)
        combo_box.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # GTK builds the list when the style of the selection changes, which it
        # notices on its own only as long as it has not displayed the selection.
        combo_box.emit('style-updated')
        combo_box.connect('popup', restrict_list, max_visible_items)
        parts = list_parts(combo_box)
        if parts is not None:
            scrolled_window, tree_view = parts
            scrolled_window.connect('notify::vscrollbar-policy', keep_list_scrollable)
            tree_view.connect('size-allocate', show_selected_item, combo_box)
