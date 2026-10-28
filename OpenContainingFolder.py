# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
#
# OpenContainingFolder.py
# Copyright (C) 2012-2016 Donagh Horgan <donagh.horgan@gmail.com>
# Partly based on rb-open-folder by Adolfo González Blázquez.
# Copyright (C) 2007, 2008 Adolfo González Blázquez <code@infinicode.org>
# Cross-desktop file selection enhancement, 2026.
#
# GPL-3.0-or-later; see LICENSE for the full license text.

from gi.repository import Gio, GLib, GObject, Peas
import logging
import subprocess

LOG = logging.getLogger(__name__)


class OpenContainingFolder(GObject.Object, Peas.Activatable):
    """Reveal a Rhythmbox selection in the system file manager."""

    object = GObject.property(type=GObject.Object)

    _action = 'open-containing-folder'
    _locations = ('browser-popup', 'playlist-popup',
                  'podcast-episode-popup', 'queue-popup')
    _bus_name = 'org.freedesktop.FileManager1'
    _object_path = '/org/freedesktop/FileManager1'

    def __init__(self):
        super().__init__()
        self._app = Gio.Application.get_default()

    @staticmethod
    def _open_parent(uri):
        """Preserve the original folder-opening behavior if reveal fails."""
        try:
            parent = Gio.File.new_for_uri(uri).get_parent()
            if parent is None:
                LOG.warning('No parent folder for %s', uri)
                return
            LOG.info('Falling back to opening parent folder: %s', parent.get_uri())
            subprocess.Popen(['xdg-open', parent.get_uri()],
                             stdin=subprocess.DEVNULL)
        except Exception:
            LOG.exception('Could not open parent folder for %s', uri)

    def _on_show_items(self, connection, result, uri):
        try:
            connection.call_finish(result)
            LOG.info('FileManager1.ShowItems accepted %s', uri)
        except GLib.Error as exc:
            LOG.warning('FileManager1.ShowItems failed: %s', exc)
            self._open_parent(uri)
        except Exception:
            LOG.exception('Unexpected FileManager1 response error')
            self._open_parent(uri)

    def _on_session_bus(self, source, result, uri):
        try:
            connection = Gio.bus_get_finish(result)
            LOG.debug('Calling FileManager1.ShowItems for %s', uri)
            connection.call(
                self._bus_name, self._object_path, self._bus_name,
                'ShowItems', GLib.Variant('(ass)', ([uri], '')),
                None, Gio.DBusCallFlags.NONE, 3000, None,
                lambda conn, res: self._on_show_items(conn, res, uri))
        except GLib.Error as exc:
            LOG.warning('Cannot access session D-Bus: %s', exc)
            self._open_parent(uri)
        except Exception:
            LOG.exception('Could not request file selection')
            self._open_parent(uri)

    def open_folder(self, *args):
        try:
            page = self.object.props.selected_page
            selected = page.get_entry_view().get_selected_entries()
            if not selected:
                return
            uri = selected[0].get_playback_uri()
            if not uri:
                LOG.warning('Selected track has no playback URI')
                return
            # The FileManager1 specification expects URIs, including for
            # ordinary local files and mounted SMB/CIFS shares.
            Gio.bus_get(Gio.BusType.SESSION, None,
                        lambda source, result: self._on_session_bus(source, result, uri))
        except Exception:
            LOG.exception('Could not reveal selected track')

    def do_activate(self):
        action = Gio.SimpleAction(name=self._action)
        action.connect('activate', self.open_folder)
        self._app.add_action(action)
        item = Gio.MenuItem()
        item.set_label('Open containing folder')
        item.set_detailed_action('app.%s' % self._action)
        for location in self._locations:
            self._app.add_plugin_menu_item(location, self._action, item)

    def do_deactivate(self):
        for location in self._locations:
            self._app.remove_plugin_menu_item(location, self._action)
        self._app.remove_action(self._action)
