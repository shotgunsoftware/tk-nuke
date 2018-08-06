# Copyright (c) 2016 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""Menu handling for Nuke and Hiero."""

import tank
import sys
import nuke
import os
import unicodedata
import nukescripts.openurl
import nukescripts

# -----------------------------------------------------------------------------

class BaseMenuGenerator(object):
    """
    The base class for Nuke based menu generators.
    """

    def __init__(self, engine, menu_name):
        """
        Initializes a new menu generator.

        :param engine: The currently-running engine.
        :type engine: :class:`tank.platform.Engine`
        :param menu_name: The name of the menu to be created.
        """
        self._engine = engine
        self._menu_name = menu_name

        engine_root_dir = self.engine.disk_location
        self._shotgun_logo = os.path.abspath(
            os.path.join(
                engine_root_dir,
                "resources",
                "sg_logo_80px.png",
            ),
        )
        self._shotgun_logo_blue = os.path.abspath(
            os.path.join(
                engine_root_dir,
                "resources",
                "sg_logo_blue_32px.png",
            ),
        )

    @property
    def engine(self):
        """
        The currently-running engine.
        """
        return self._engine

    @property
    def menu_name(self):
        """
        The name of the menu to be generated.
        """
        return self._menu_name

    def create_sgtk_error_menu(self):
        """
        Creates an "error" menu item.
        """
        (exc_type, exc_value, exc_traceback) = sys.exc_info()
        msg = ("Message: Shotgun encountered a problem starting the Engine.\n"
               "Exception: %s - %s\n"
               "Traceback (most recent call last): %s" % (exc_type,
                                                          exc_value,
                                                          "\n".join(traceback.format_tb(exc_traceback))))

        self._disable_menu("[Toolkit Error - Click for details]", msg)

    def create_sgtk_disabled_menu(self, details=""):
        """
        Creates a "disabled" Shotgun menu item.

        :param details: A detailed message about why Toolkit has been
                        disabled.
        """
        msg = ("Shotgun integration is currently disabled because the file you "
               "have opened is not recognized. Shotgun cannot "
               "determine which Context the currently-open file belongs to. "
               "In order to enable Toolkit integration, try opening another "
               "file. <br><br><i>Details:</i> %s" % details)
        self._disable_menu("[Toolkit is disabled - Click for details]", msg)

    def create_disabled_menu(self, cmd_name, msg):
        """
        Implemented in deriving classes to create a "disabled" menu.

        :param cmd_name:    An AppCommand object to associate with the disabled
                            menu command.
        :param msg:         A message explaining why Toolkit is disabled.
        """
        self.engine.logger.debug(
            'Not implemented: %s.%s',
            self.__class__.__name__,
            'create_disabled_menu'
        )

    def _disable_menu(self, cmd_name, msg):
        """
        Disables the Shotgun menu.

        :param cmd_name:    An AppCommand object to associate with the disabled
                            menu command.
        :param msg:         A message explaining why Toolkit is disabled.
        """
        if self._menu_handle:
            self.destroy_menu()
        self.create_disabled_menu(cmd_name, msg)

    def _jump_to_sg(self):
        """
        Jump from a context to Shotgun.
        """
        from tank.platform.qt import QtCore, QtGui
        url = self.engine.context.shotgun_url
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _jump_to_fs(self):
        """
        Jump from a context to the filesystem.
        """
        paths = self.engine.context.filesystem_locations
        for disk_location in paths:
            system = sys.platform
            if system == "linux2":
                cmd = 'xdg-open "%s"' % disk_location
            elif system == "darwin":
                cmd = 'open "%s"' % disk_location
            elif system == "win32":
                cmd = 'cmd.exe /C start "Folder" "%s"' % disk_location
            else:
                raise OSError("Platform '%s' is not supported." % system)

            exit_code = os.system(cmd)
            if exit_code != 0:
                self.engine.logger.error("Failed to launch '%s'!", cmd)

# -----------------------------------------------------------------------------

class HieroMenuGenerator(BaseMenuGenerator):
    """
    A Hiero specific menu generator.
    """
    def __init__(self, engine, menu_name):
        """
        Initializes a new menu generator.

        :param engine: The currently-running engine.
        :type engine: :class:`tank.platform.Engine`
        :param menu_name: The name of the menu to be created.
        """
        super(HieroMenuGenerator, self).__init__(engine, menu_name)
        self._menu_handle = None
        self._context_menus_to_apps = dict()

    def _create_hiero_menu(self, add_commands=True, commands=None):
        """
        Creates the "Shotgun" menu in Hiero.

        :param bool add_commands: If True, menu commands will be added to the
            newly-created menu. If False, the menu will be created, but no
            contents will be added. Defaults to True.
        :param dict commands: The engine commands to add to the various menus.
            The dictionary is structured the same as engine.commands is, where
            the key is the name of the command, and the value is a dictionary
            of command properties.
        """
        import hiero
        if self._menu_handle is not None:
            self.destroy_menu()

        from sgtk.platform.qt import QtGui

        self._menu_handle = QtGui.QMenu("Shotgun")
        help = hiero.ui.findMenuAction("Cache")
        menuBar = hiero.ui.menuBar()
        menuBar.insertMenu(help, self._menu_handle)

        self._menu_handle.clear()

        # If we were asked not to add any commands to the menu,
        # then bail out.
        if not add_commands:
            return

        # Now add the context item on top of the main menu.
        self._context_menu = self._add_context_menu()
        self._menu_handle.addSeparator()

        if not commands:
            return

        # Now enumerate all items and create menu objects for them.
        menu_items = []
        for (cmd_name, cmd_details) in commands.items():
            menu_items.append(HieroAppCommand(self.engine, cmd_name, cmd_details))

        # Now add favourites.
        for fav in self.engine.get_setting("menu_favourites"):
            app_instance_name = fav["app_instance"]
            menu_name = fav["name"]
            # Scan through all menu items.
            for cmd in menu_items:
                if cmd.app_instance_name == app_instance_name and cmd.name == menu_name:
                    # Found our match!
                    cmd.add_command_to_menu(self._menu_handle)
                    # Mark as a favourite item.
                    cmd.favourite = True

        # Get the apps for the various context menus.
        self._context_menus_to_apps = {
            "bin_context_menu": [],
            "timeline_context_menu": [],
            "spreadsheet_context_menu": [],
        }

        remove = set()
        for (key, apps) in self._context_menus_to_apps.iteritems():
            items = self.engine.get_setting(key)
            for item in items:
                app_instance_name = item["app_instance"]
                menu_name = item["name"]
                # Scan through all menu items.
                for (i, cmd) in enumerate(menu_items):
                    if cmd.app_instance_name == app_instance_name and cmd.name == menu_name:
                        # Found the match.
                        apps.append(cmd)
                        cmd.requires_selection = item["requires_selection"]
                        if not item["keep_in_menu"]:
                            remove.add(i)
                        break

        for index in sorted(remove, reverse=True):
            del menu_items[index]

        # Register for the interesting events.
        hiero.core.events.registerInterest(
            "kShowContextMenu/kBin",
            self.eventHandler,
        )
        hiero.core.events.registerInterest(
            "kShowContextMenu/kTimeline",
            self.eventHandler,
        )
        # Note that the kViewer works differently than the other things
        # (returns a hiero.ui.Viewer object: http://docs.thefoundry.co.uk/hiero/10/hieropythondevguide/api/api_ui.html#hiero.ui.Viewer)
        # so we cannot support this easily using the same principles as for the other things.
        hiero.core.events.registerInterest(
            "kShowContextMenu/kSpreadsheet",
            self.eventHandler,
        )
        self._menu_handle.addSeparator()

        # Now go through all of the menu items.
        # Separate them out into various sections.
        commands_by_app = {}

        for cmd in menu_items:
            if cmd.type == "context_menu":
                cmd.add_command_to_menu(self._context_menu)
            else:
                # Normal menu.
                app_name = cmd.app_name
                if app_name is None:
                    # Unparented app.
                    app_name = "Other Items"
                if not app_name in commands_by_app:
                    commands_by_app[app_name] = []
                commands_by_app[app_name].append(cmd)

        # Now add all apps to main menu.
        self._add_app_menu(commands_by_app)

    def create_menu(self, add_commands=True):
        """
        Creates the "Shotgun" menu in Hiero.

        :param add_commands:    If True, menu commands will be added to
                                the newly-created menu. If False, the menu
                                will be created, but no contents will be
                                added. Defaults to True.
        """
        self._create_hiero_menu(add_commands=add_commands, commands=self.engine.commands)

    def destroy_menu(self):
        """
        Destroys the "Shotgun" menu.
        """
        import hiero
        menuBar = hiero.ui.menuBar()
        menuBar.removeAction(self._menu_handle.menuAction())
        self._menu_handle.clear()
        self._menu_handle = None

        # Register for the interesting events.
        hiero.core.events.unregisterInterest(
            "kShowContextMenu/kBin",
            self.eventHandler,
        )
        hiero.core.events.unregisterInterest(
            "kShowContextMenu/kTimeline",
            self.eventHandler,
        )
        # Note that the kViewer works differently than the other things
        # (returns a hiero.ui.Viewer object: http://docs.thefoundry.co.uk/hiero/10/hieropythondevguide/api/api_ui.html#hiero.ui.Viewer)
        # so we cannot support this easily using the same principles as for the other things.
        hiero.core.events.unregisterInterest(
            "kShowContextMenu/kSpreadsheet",
            self.eventHandler,
        )

    def eventHandler(self, event):
        """
        The engine's Hiero-specific event handler. This is called by Hiero when
        events are triggered, which then handles running SGTK-specific event
        behaviors.

        :param event:   The Hiero event object that was triggered.
        """
        if event.subtype == "kBin":
            cmds = self._context_menus_to_apps["bin_context_menu"]
        elif event.subtype == "kTimeline":
            cmds = self._context_menus_to_apps["timeline_context_menu"]
        elif event.subtype == "kSpreadsheet":
            cmds = self._context_menus_to_apps["spreadsheet_context_menu"]

        if not cmds:
            return

        event.menu.addSeparator()
        menu = event.menu.addAction("Shotgun")
        menu.setEnabled(False)

        for cmd in cmds:
            enabled = True
            if cmd.requires_selection:
                if hasattr(event.sender, "selection") and not event.sender.selection():
                    enabled = False
            cmd.sender = event.sender
            cmd.event_type = event.type
            cmd.event_subtype = event.subtype
            cmd.add_command_to_menu(event.menu, enabled)
        event.menu.addSeparator()

    def _add_context_menu(self):
        """
        Adds a context menu which displays the current context.
        """
        ctx = self.engine.context

        if ctx.entity is None:
            ctx_name = "%s" % ctx.project["name"]
        elif ctx.step is None and ctx.task is None:
            # entity only
            # e.g. Shot ABC_123
            ctx_name = "%s %s" % (ctx.entity["type"], ctx.entity["name"])
        else:
            # we have either step or task
            task_step = None
            if ctx.step:
                task_step = ctx.step.get("name")
            if ctx.task:
                task_step = ctx.task.get("name")

            # e.g. [Lighting, Shot ABC_123]
            ctx_name = "%s, %s %s" % (task_step, ctx.entity["type"], ctx.entity["name"])

        # create the menu object
        ctx_menu = self._menu_handle.addMenu(ctx_name)
        action = ctx_menu.addAction("Jump to Shotgun")
        action.triggered.connect(self._jump_to_sg)

        if ctx.filesystem_locations:
            action = ctx_menu.addAction("Jump to File System")
            action.triggered.connect(self._jump_to_fs)

        ctx_menu.addSeparator()
        return ctx_menu

    def _add_app_menu(self, commands_by_app):
        """
        Add all apps to the main menu.

        :param commands_by_app: A dict containing a key for each active
                                app paired with its AppCommand object to be
                                added to the menu.
        """
        for app_name in sorted(commands_by_app.keys()):
            if len(commands_by_app[app_name]) > 1:
                # more than one menu entry fort his app
                # make a sub menu and put all items in the sub menu
                app_menu = self._menu_handle.addMenu(app_name)
                for cmd in commands_by_app[app_name]:
                    cmd.add_command_to_menu(app_menu)
            else:
                # this app only has a single entry.
                # display that on the menu
                # todo: Should this be labeled with the name of the app
                # or the name of the menu item? Not sure.
                cmd_obj = commands_by_app[app_name][0]
                if not cmd_obj.favourite:
                    # skip favourites since they are already on the menu
                    cmd_obj.add_command_to_menu(self._menu_handle)

# -----------------------------------------------------------------------------

class NukeStudioMenuGenerator(HieroMenuGenerator):
    """
    A Nuke Studio specific menu generator.
    """
    def _is_node_command(self, cmd_name, cmd_details):
        """
        Tests whether a given engine command is a "node" type command or not.

        :param str cmd_name: The name of the engine command.
        :param dict cmd_details: The engine command's properties dictionary.

        :rtype: bool
        """
        return NukeAppCommand(self.engine, cmd_name, cmd_details).type == "node"

    def create_menu(self, add_commands=True):
        """
        Adds all engine commands to one of various menus in Nuke Studio.

        :param bool add_commands: If True, menus will be created and menu items
            added for all engine commands. If False, the menus will be created,
            but will not be populated with engine commands.
        """
        # We're going to divide up the engine command. For "node" type commands,
        # which are commands from apps like tk-nuke-quickdailies, or tk-nuke-writenode,
        # we register them in the Nuke-style node context menu. For everything else, we
        # just pass them on to the standard Hiero-style menu creation logic.
        node_commands = dict()
        non_node_commands = dict()

        for cmd_name, cmd_details in self.engine.commands.items():
            if self._is_node_command(cmd_name, cmd_details):
                node_commands[cmd_name] = cmd_details
            else:
                non_node_commands[cmd_name] = cmd_details

        self._create_hiero_menu(add_commands=add_commands, commands=non_node_commands)

        node_menu_handle = nuke.menu("Nodes").addMenu(self._menu_name, icon=self._shotgun_logo)
        node_menu_handle.clearMenu()

        if not add_commands:
            return

        for (cmd_name, cmd_details) in node_commands.items():
            cmd = NukeAppCommand(self.engine, cmd_name, cmd_details)

            # Get icon if specified - default to tank icon if not specified.
            icon = cmd.properties.get("icon", self._shotgun_logo)
            command_context = cmd.properties.get("context")

            # If the app recorded a context that it wants the command to be associated
            # with, we need to check it against the current engine context. If they
            # don't match then we don't add it.
            if command_context is None or command_context is self.engine.context:
                node_menu_handle.addCommand(cmd.name, cmd.callback, icon=icon)

    def create_disabled_menu(self, cmd_name, msg):
        """
        Creates the contents of the "disabled" menu in Nuke Studio.

        :param cmd_name:    An AppCommand object to associate with the disabled
                            menu command.
        :param msg:         A message explaining why Toolkit is disabled.
        """
        self.create_menu(add_commands=False)

        import nuke
        callback = lambda m = msg: nuke.message(m)
        cmd = HieroAppCommand(
            self.engine,
            cmd_name,
            dict(properties=dict(), callback=callback),
        )
        cmd.add_command_to_menu(self._menu_handle, icon=self._shotgun_logo_blue)

# -----------------------------------------------------------------------------

class NukeMenuGenerator(BaseMenuGenerator):
    """
    A Nuke specific menu generator.
    """
    def __init__(self, engine, menu_name):
        """
        Initializes a new menu generator.

        :param engine: The currently-running engine.
        :type engine: :class:`tank.platform.Engine`
        :param menu_name: The name of the menu to be created.
        """
        super(NukeMenuGenerator, self).__init__(engine, menu_name)
        self._dialogs = []

    def create_menu(self, add_commands=True):
        """
        Creates the "Shotgun" menu in Nuke.

        :param add_commands:    If True, menu commands will be added to
                                the newly-created menu. If False, the menu
                                will be created, but no contents will be
                                added. Defaults to True.
        """
        # Create main Shotgun menu.
        menu_handle = nuke.menu("Nuke").addMenu(self._menu_name)
        node_menu_handle = nuke.menu("Nodes").addMenu(self._menu_name, icon=self._shotgun_logo)

        # Slight hack here, but first ensure that menus are empty.
        # This is to ensure we can recover from weird context switches
        # where the engine didn't clean up after itself properly.
        menu_handle.clearMenu()
        node_menu_handle.clearMenu()

        # If we were asked not to add any commands to the menu,
        # the bail out.
        if not add_commands:
            return

        # Now add the context item on top of the main menu.
        self._context_menu = self._add_context_menu(menu_handle)
        menu_handle.addSeparator()

        # Now enumerate all items and create menu objects for them.
        menu_items = []
        for (cmd_name, cmd_details) in self.engine.commands.items():
             menu_items.append(NukeAppCommand(self.engine, cmd_name, cmd_details))

        # Sort the list of commands in name order.
        menu_items.sort(key=lambda x: x.name)

        # Now add favourites.
        for fav in self.engine.get_setting("menu_favourites"):
            app_instance_name = fav["app_instance"]
            menu_name = fav["name"]
            hotkey = fav.get("hotkey")

            # Scan through all menu items.
            for cmd in menu_items:
                 if cmd.app_instance_name == app_instance_name and cmd.name == menu_name:
                     # Found our match!
                     cmd.add_command_to_menu(menu_handle, hotkey=hotkey)
                     # Mark as a favourite item.
                     cmd.favourite = True
        menu_handle.addSeparator()
        
        # Now go through all of the menu items.
        # Separate them out into various sections.
        commands_by_app = {}
        
        for cmd in menu_items:
            if cmd.type == "node":
                # Get icon if specified - default to tank icon if not specified.
                icon = cmd.properties.get("icon", self._shotgun_logo)
                command_context = cmd.properties.get("context")

                # If the app recorded a context that it wants the command to be associated
                # with, we need to check it against the current engine context. If they
                # don't match then we don't add it.
                if command_context is None or command_context is self.engine.context:
                    node_menu_handle.addCommand(cmd.name, cmd.callback, icon=icon)
            elif cmd.type == "context_menu":
                cmd.add_command_to_menu(self._context_menu)
            else:
                # Normal menu.
                app_name = cmd.app_name
                if app_name is None:
                    # Unparented app.
                    app_name = "Other Items" 
                if not app_name in commands_by_app:
                    commands_by_app[app_name] = []
                commands_by_app[app_name].append(cmd)

            # In addition to being added to the normal menu above,
            # panel menu items are also added to the pane menu.
            if cmd.type == "panel":
                # First make sure the Shotgun pane menu exists.
                pane_menu = nuke.menu("Pane").addMenu(
                    "Shotgun",
                    icon=self._shotgun_logo,
                )
                # Now set up the callback.
                cmd.add_command_to_pane_menu(pane_menu)
        
        # Now add all apps to main menu.
        self._add_app_menu(commands_by_app, menu_handle)

    def create_disabled_menu(self, cmd_name, msg):
        """
        Creates the contents of the "disabled" menu in Nuke.

        :param cmd_name:    An AppCommand object to associate with the disabled
                            menu command.
        :param msg:         A message explaining why Toolkit is disabled.
        """
        self.create_menu(add_commands=False)

        import nuke
        callback = lambda m = msg: nuke.message(m)
        cmd = NukeAppCommand(
            self.engine,
            cmd_name,
            dict(properties=dict(), callback=callback),
        )
        cmd.add_command_to_menu(self._menu_handle, icon=self._shotgun_logo_blue)

    def destroy_menu(self):
        """
        Destroys any menus that were created.
        """
        # Important!
        # The menu code in nuke seems quite unstable, so make sure to test 
        # any changes done in relation to menu deletion carefully.
        # the removeItem() method seems to work on some version of Nuke, but not all.
        # For example, the following code works in nuke 7, not nuke 6:
        # nuke.menu("Nuke").removeItem("Shotgun")
        
        # The strategy below is to be as safe as possible, acquire a handle to 
        # the menu by iteration (if you store the handle object, they may expire
        # and when you try to access them they underlying object is gone and things 
        # will crash). The clearMenu() method seems to work on both v6 and v7.
        menus = ["Nuke", "Pane", "Nodes"]
        for menu in menus:
            # Find the menu and iterate over all items.
            for mh in nuke.menu(menu).items():
                # Look for the shotgun menu.
                if isinstance(mh, nuke.Menu) and mh.name() == self._menu_name:
                    # Clear it.
                    mh.clearMenu()

    def _add_context_menu(self, menu_handle):
        """
        Adds a context menu which displays the current context.

        :param menu_handle: A handle to Nuke's top-level menu manager object.
        """        
        ctx = self.engine.context
        ctx_name = str(ctx)

        # Create the menu object.
        ctx_menu = menu_handle.addMenu(ctx_name, icon=self._shotgun_logo_blue)
        ctx_menu.addCommand("Jump to Shotgun", self._jump_to_sg)
        if ctx.filesystem_locations:
            ctx_menu.addCommand("Jump to File System", self._jump_to_fs)
        ctx_menu.addSeparator()
        return ctx_menu

    def _add_app_menu(self, commands_by_app, menu_handle):
        """
        Add all apps to the main menu, process them one by one.

        :param commands_by_app: A dict containing a key for each active
                                app paired with its AppCommand object to be
                                added to the menu.
        :param menu_handle:     A handle to Nuke's top-level menu manager object.
        """
        for app_name in sorted(commands_by_app.keys()):
            if len(commands_by_app[app_name]) > 1:
                # More than one menu entry for this app.
                # Make a sub menu and put all items in the sub menu.
                app_menu = menu_handle.addMenu(app_name)
                
                # Get the list of menu cmds for this app.
                cmds = commands_by_app[app_name]
                # Make sure it is in alphabetical order.
                cmds.sort(key=lambda x: x.name) 
                
                for cmd in cmds:
                    cmd.add_command_to_menu(app_menu)
            else:
                # This app only has a single entry.
                # TODO: Should this be labelled with the name of the app 
                # or the name of the menu item? Not sure.
                cmd_obj = commands_by_app[app_name][0]
                if not cmd_obj.favourite:
                    # Skip favourites since they are already on the menu.
                    cmd_obj.add_command_to_menu(menu_handle)

# -----------------------------------------------------------------------------

class BaseAppCommand(object):
    """
    The base class for command wrappers for various Nuke modes.
    This wraps a single command that is received from engine.commands.
    """
    def __init__(self, engine, name, command_dict):
        """
        Initializes a new BaseAppCommand.

        :param engine: The currently-running engine.
        :type engine: :class:`tank.platform.Engine`
        :param name: The name of the command.
        :param command_dict: The properties dictionary of the command.
        """
        self._name = name
        self._engine = engine
        self._properties = command_dict["properties"]
        self._callback = command_dict["callback"]
        self._favourite = False
        self._app = self._properties.get("app")
        self._type = self._properties.get("type", "default")
        try:
            self._app_name = self._app.display_name
        except AttributeError:
            self._app_name = None
        self._app_instance_name = None
        if self._app:
            for (app_instance_name, app_instance_obj) in engine.apps.items():
                if self._app and self._app == app_instance_obj:
                    self._app_instance_name = app_instance_name

    @property
    def app(self):
        """The command's parent app."""
        return self._app

    @property
    def app_instance_name(self):
        """The instance name of the parent app."""
        return self._app_instance_name

    @property
    def app_name(self):
        """The name of the parent app."""
        return self._app_name

    @property
    def name(self):
        """The name of the command."""
        return self._name

    @name.setter
    def name(self, name):
        self._name = str(name)

    @property
    def engine(self):
        """The currently-running engine."""
        return self._engine

    @property
    def properties(self):
        """The command's properties dictionary."""
        return self._properties

    @property
    def callback(self):
        """The callback function associated with the command."""
        return self._callback

    @callback.setter
    def callback(self, cb):
        self._callback = cb

    @property
    def favourite(self):
        """Whether the command is a favourite."""
        return self._favourite

    @favourite.setter
    def favourite(self, state):
        self._favourite = bool(state)

    @property
    def type(self):
        """The command's type as a string."""
        return self._type

    def add_command_to_menu(self, menu, enabled=True, icon=None):
        raise NotImplementedError()

    def add_command_to_pane_menu(self, menu):
        raise NotImplementedError()

    def get_documentation_url_str(self):
        """
        Returns the documentation URL.
        """
        if self.app:
            doc_url = self.app.documentation_url
            # Deal with nuke's inability to handle unicode.
            if doc_url.__class__ == unicode:
                doc_url = unicodedata.normalize("NFKD", doc_url).encode("ascii", "ignore")
            return doc_url
        return None

# -----------------------------------------------------------------------------

class HieroAppCommand(BaseAppCommand):
    """
    Wraps a single command that you get from engine.commands.
    """
    def __init__(self, engine, name, command_dict):
        """
        Initializes a new AppCommand object.

        :param engine:  The SGTK engine controlling the session.
        :param name:    The name of the command.
        :command_dict:  A dict containing the information necessary to
                        register a command with Hiero's menu manager. This
                        includes a properties dict as well as a callback
                        in the form of a callable object.
        """
        super(HieroAppCommand, self).__init__(engine, name, command_dict)
        self._requires_selection = False
        self._sender = None
        self._event_type = None
        self._event_subtype = None

    @property
    def requires_selection(self):
        """
        Whether the command requires something to be selected
        in order to be executed.
        """
        return self._requires_selection

    @requires_selection.setter
    def requires_selection(self, state):
        self._requires_selection = bool(state)

    @property
    def sender(self):
        return self._sender

    @sender.setter
    def sender(self, sender):
        self._sender = sender

    @property
    def event_type(self):
        return self._event_type

    @event_type.setter
    def event_type(self, event_type):
        self._event_type = event_type

    @property
    def event_subtype(self):
        return self._event_subtype

    @event_subtype.setter
    def event_subtype(self, event_subtype):
        self._event_subtype = event_subtype

    def add_command_to_menu(self, menu, enabled=True, icon=None):
        """
        Adds the command to the menu.

        :param menu:    A handle to the menu to add the command to.
        :param enabled: Whether the command is to be enabled once it
                        is added to the menu. Defaults to True.
        :param icon:    The path to an image to use as the icon for the
                        command.
        """
        icon = icon or self.properties.get("icon")
        action = menu.addAction(self.name)
        action.setEnabled(enabled)
        if icon:
            from sgtk.platform.qt import QtGui
            action.setIcon(QtGui.QIcon(icon))

        def handler():
            # Populate special action context, which is read by apps and hooks.
            # In hiero, the sender parameter for hiero.core.events.EventType.kShowContextMenu
            # is supposed to always of class binview:
            #
            # http://docs.thefoundry.co.uk/hiero/10/hieropythondevguide/api/api_ui.html?highlight=sender#hiero.ui.BinView
            #
            # In reality, however, it seems it returns the following items:
            # ui.Hiero.Python.TimelineEditor object at 0x11ab15248
            # ui.Hiero.Python.SpreadsheetView object at 0x11ab152d8>
            # ui.Hiero.Python.BinView
            #
            # These objects all have a selection property that returns a list of objects.
            # We extract the selected objects and set the engine "last clicked" state:
            
            # Set the engine last clicked selection state.
            if self.sender:
                self.engine._last_clicked_selection = self.sender.selection()
            else:
                # Main menu.
                self.engine._last_clicked_selection = []
            
            # Set the engine last clicked selection area.
            if self.event_type == "kBin":
                self.engine._last_clicked_area = self.engine.HIERO_BIN_AREA
            elif self.event_type == "kTimeline":
                self.engine._last_clicked_area = self.engine.HIERO_TIMELINE_AREA
            elif self.event_type == "kSpreadsheet":
                self.engine._last_clicked_area = self.engine.HIERO_SPREADSHEET_AREA
            else:
                self.engine._last_clicked_area = None
            
            self.engine.logger.debug("")
            self.engine.logger.debug("--------------------------------------------")
            self.engine.logger.debug("A menu item was clicked!")
            self.engine.logger.debug("Event Type: %s / %s", self.event_type, self.event_subtype)
            self.engine.logger.debug("Selected Objects:")

            for x in self.engine._last_clicked_selection:
                self.engine.logger.debug("- %r", x)
            self.engine.logger.debug("--------------------------------------------")
            
            # Fire the callback.
            self.callback()
        action.triggered.connect(handler)

# -----------------------------------------------------------------------------

class NukeAppCommand(BaseAppCommand):
    """
    Wraps a single command that you get from engine.commands.
    """
    def __init__(self, *args, **kwargs):
        super(NukeAppCommand, self).__init__(*args, **kwargs)
        self._original_callback = self._callback
        self.callback = self._non_pane_menu_callback_wrapper

    def _non_pane_menu_callback_wrapper(self):
        """
        Callback for all non-pane menu commands.
        """
        # This is a wrapped menu callback for whenever an item is clicked
        # in a menu which isn't the standard nuke pane menu. This ie because 
        # the standard pane menu in nuke provides nuke with an implicit state
        # so that nuke knows where to put the panel when it is created.
        # If the command is called from a non-pane menu however, this implicity
        # state does not exist and needs to be explicity defined.
        #
        # For this purpose, we set a global flag to hint to the panelling 
        # logic to run its special window logic in this case.
        #
        # Note that because of nuke not using the import_module()
        # system, it's hard to obtain a reference to the engine object
        # right here - this is why we set a flag on the main tank
        # object like this.
        setattr(tank, "_callback_from_non_pane_menu", True)
        try:
            self._original_callback()
        finally:
            try:
                delattr(tank, "_callback_from_non_pane_menu")
            except AttributeError:
                pass
        
    def add_command_to_pane_menu(self, menu):
        """
        Add a command to the pane menu.
        
        :param menu: The menu object to add the new item to.
        """
        icon = self.properties.get("icon")
        menu.addCommand(self.name, self._original_callback, icon=icon)

    def add_command_to_menu(self, menu, enabled=True, icon=None, hotkey=None):
        """
        Adds a command to the menu.
        
        :param menu:    The menu object to add the new item to.
        :param enabled: Whether the command will be enabled after it
                        is added to the menu. Defaults to True.
        :param icon:    The path to an image file to use as the icon
                        for the menu command.
        """
        icon = icon or self.properties.get("icon")
        hotkey = hotkey or self.properties.get("hotkey")

        # Now wrap the command callback in a wrapper (see above)
        # which sets a global state variable. This is detected
        # by the show_panel so that it can correctly establish 
        # the flow for when a pane menu is clicked and you want
        # the potential new panel to open in that window.
        #
        # NOTE: setting the new callback lambda on the object to resolve
        # a crash on close happening in Nuke 11. Likely a GC issue, and having
        # the callable associated with an object resolves it.
        if hotkey:
            menu.addCommand(self.name, self.callback, hotkey, icon=icon)
        else:
            menu.addCommand(self.name, self.callback, icon=icon)

# -----------------------------------------------------------------------------

