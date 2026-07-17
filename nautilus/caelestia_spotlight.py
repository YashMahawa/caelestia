"""Expose Caelestia Spotlight from Nautilus context menus."""

import subprocess

from gi.repository import GObject, Nautilus


class CaelestiaSpotlight(GObject.GObject, Nautilus.MenuProvider):
    def _open(self, _item, *_args):
        subprocess.Popen(
            ["/home/yash/.local/bin/caelestia-launcher"],
            start_new_session=True,
        )

    def _item(self):
        item = Nautilus.MenuItem(
            name="CaelestiaSpotlight::search",
            label="Search with Caelestia Spotlight",
            tip="Search apps, folders, filenames, document contents and meaning",
            icon="system-search-symbolic",
        )
        item.connect("activate", self._open)
        return item

    def get_background_items(self, current_folder):
        return [self._item()]

    def get_file_items(self, files):
        return [self._item()]
