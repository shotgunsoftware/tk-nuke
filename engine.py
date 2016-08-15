# Copyright (c) 2016 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import tank
import platform
import time
import nuke
import os
import re
import traceback
import unicodedata
import nukescripts

class NukeEngine(tank.platform.Engine):
    """
    An engine that supports Nuke 6.3v5+, Hiero 9.0+, and Nuke Studio 9.0+

    **Bootstrap Flow**

    The code path for the bootstrap routine for Nuke, Nuke Studio, and Hiero is quite
    complex due to the support of all three modes of the application.

    - All three Nuke modes make use of the "generic" bootstrap routine in
      tk-multi-launchapp. There is still Nuke- and Hiero-specific logic in
      that app, but it is there for the sake of backwards compatibility
      should someone still be using the tk-hiero engine or an old version
      of tk-nuke.

    - There are, in essence, two code paths for the bootstrap: Nuke in one and
      Hiero/Nuke Studio in the other. Nuke Studio acts much more like Hiero than it
      does Nuke, and as such shares many similarities when it comes to the bootstrap
      process.

    Step 1:
        The tk-multi-launchapp app will go into its "generic" bootstrap routine and
        will look in the engine structure for `tk-nuke/python/startup/bootstrap.py`.
        This is the first block of logic that will be executed, regardless of whether
        it is Nuke, Nuke Studio, or Hiero that is being launched. This logic handles
        setting either the NUKE_PATH or HIERO_PLUGIN_PATH environment variables,
        depending on which mode is being launched.

    Step 2:
        With the appropriate path variable set in #1, the `tk-nuke/python/startup`
        directory is now available to Nuke at launch as a location to look for both
        `init.py` and `menu.py` scripts to be run on launch. It's worth noting that
        the order of operations for Nuke (regardless of mode) is to execute init.py
        first, before the GUI is loaded, and menu.py later after most of the Nuke
        application is up and running and any file loads have completed.

    Step 3:
        Startup of the DCC application is under way at this point. If Nuke is launching
        in a no-UI mode, then the `init.py` is responsible for continuing the bootstrap,
        otherwise `tk-nuke/python/startup/menu.py` is in charge. In either case, the
        `tk-nuke/python/startup` directory is added to `sys.path` and its `sgtk_startup.py`
        module is loaded, which executes its own `bootstrap_sgtk()` function.

    Step 4:
        The `bootstrap_sgtk()` function handles initializing SGTK and starting up
        the tk-nuke engine.

    .. NOTE:: There is also an addition made to the `NUKE_PATH` environment variable
              in the engine initialization routine here in `engine.py`. This adds the
              root-level `tk-nuke/startup` directory, which contains a `menu.py` that
              is utilized during script load in the Nuke mode of the DCC. This is needed
              because the bootstrap routine outlined in the steps above only occurs at
              launch time, but NOT on script open. This is an important distinction, because
              each file open operation Nuke performs spawns a new process, which itself needs
              to then have the engine's `tk-nuke/python` directory added to `sys.path`.

    **Nuke Event Callbacks**

    During the bootstrap process described above, event callbacks are registered with
    Nuke. The events of interest are OnScriptLoad and OnScriptSave. Interest is registered
    in these events in `tk-nuke/python/tk_nuke/__init__.py`, which is also where the
    callbacks themselves are defined.
    """

    # Define the different areas where menu events can occur in Hiero.
    (HIERO_BIN_AREA, HIERO_SPREADSHEET_AREA, HIERO_TIMELINE_AREA) = range(3)

    def __init__(self, *args, **kwargs):
        # For the short term, we will treat Nuke Studio as if it
        # is Hiero. This logic will change once we have true Nuke
        # Studio support for this engine.
        self._hiero_enabled = nuke.env.get("hiero")
        self._studio_enabled = nuke.env.get("studio")
        self._ui_enabled = nuke.env.get("gui")
        self._context_switcher = None
        self._menu_generator = None
        self._context_change_menu_rebuild = True
        self._processed_paths = []
        self._processed_environments = []

        super(NukeEngine, self).__init__(*args, **kwargs)

    #####################################################################################
    # Properties

    @property
    def has_ui(self):
        """
        Whether Nuke is running as a GUI/interactive session.
        """
        return self._ui_enabled

    @property
    def hiero_enabled(self):
        """
        Whether Nuke is running in Hiero mode.
        """
        return self._hiero_enabled

    @property
    def studio_enabled(self):
        """
        Whether Nuke is running in Studio mode.
        """
        return self._studio_enabled

    @property
    def context_change_allowed(self):
        """
        Whether the engine allows a context change without the need for a restart.
        """
        return True

    @property
    def menu_generator(self):
        return self._menu_generator

    #####################################################################################
    # Engine Initialization and Destruction
    
    def init_engine(self):
        """
        Called at Engine startup.
        """
        self.log_debug("%s: Initializing..." % self)

        # We need to check to make sure that we are using one of the
        # supported versions of Nuke. Right now that is anything between
        # 6.3v5 and 9.0v*. For versions higher than what we know we
        # support we'll simply warn and continue. For older versions
        # we will have to bail out, as we know they won't work properly.
        nuke_version = (
            nuke.env.get("NukeVersionMajor"),
            nuke.env.get("NukeVersionMinor"),
            nuke.env.get("NukeVersionRelease")
        )

        msg = "Nuke 6.3v5 is the minimum version supported!"
        if nuke_version[0] < 6:
            self.log_error(msg)
            return
        elif nuke_version[0] == 6 and nuke_version[1] < 3:
            self.log_error(msg)
            return
        elif nuke_version[0] == 6 and nuke_version[1] == 3 and nuke_version[2] < 5:
            self.log_error(msg)
            return

        # Versions > 9.0 have not yet been tested so show a message to that effect.
        if nuke_version[0] > 10 or (nuke_version[0] == 10 and nuke_version[1] > 1):
            # This is an untested version of Nuke.
            msg = ("The Shotgun Pipeline Toolkit has not yet been fully tested with Nuke %d.%dv%d. "
                   "You can continue to use the Toolkit but you may experience bugs or "
                   "instability.  Please report any issues you see to support@shotgunsoftware.com" 
                   % (nuke_version[0], nuke_version[1], nuke_version[2]))
            
            # Show nuke message if in UI mode, this is the first time the engine has been started
            # and the warning dialog isn't overriden by the config. Note that nuke.message isn't
            # available in Hiero, so we have to skip this there.
            if (self.has_ui 
                and not "TANK_NUKE_ENGINE_INIT_NAME" in os.environ
                and nuke_version[0] >= self.get_setting("compatibility_dialog_min_version", 11)
                and not self.hiero_enabled):
                nuke.message("Warning - Shotgun Pipeline Toolkit!\n\n%s" % msg)
                           
            # Log the warning.
            self.log_warning(msg)

        # Make sure we are not running Nuke PLE!
        if nuke.env.get("ple"):
            self.log_error("The Nuke Engine does not work with the Nuke PLE!")
            return

        # Now check that there is a location on disk which corresponds to the context.
        if self.context.project is None:
            # Must have at least a project in the context to even start!
            raise tank.TankError("The nuke engine needs at least a project"
                                 "in the context in order to start! Your "
                                 "context: %s" % self.context)

        # Do our mode-specific initializations.
        if self.hiero_enabled:
            self.init_engine_hiero()
        elif self.studio_enabled:
            self.init_engine_studio()
        else:
            self.init_engine_nuke()

    def init_engine_studio(self):
        """
        The Nuke Studio specific portion of engine initialization.
        """
        self.init_engine_hiero()

    def init_engine_hiero(self):
        """
        The Hiero-specific portion of engine initialization.
        """
        self._last_clicked_selection = []
        self._last_clicked_area = None

    def init_engine_nuke(self):
        """
        The Nuke-specific portion of engine initialization.
        """
        # Now prepare tank so that it will be picked up by any new processes
        # created by file->new or file->open.
        # Store data needed for bootstrapping Tank in env vars. Used in startup/menu.py.
        os.environ["TANK_NUKE_ENGINE_INIT_NAME"] = self.instance_name
        os.environ["TANK_NUKE_ENGINE_INIT_CONTEXT"] = tank.context.serialize(self.context)
        os.environ["TANK_NUKE_ENGINE_INIT_PROJECT_ROOT"] = self.tank.project_path
        
        # Add our startup path to the nuke init path
        startup_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "startup"))
        tank.util.append_path_to_env_var("NUKE_PATH", startup_path)        
    
        # We also need to pass the path to the python folder down to the init script
        # because nuke python does not have a __file__ attribute for that file.
        local_python_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "python"))
        os.environ["TANK_NUKE_ENGINE_MOD_PATH"] = local_python_path

    def pre_app_init(self):
        """
        Called at startup, but after QT has been initialized.
        """
        if self.hiero_enabled or self.studio_enabled:
            return

        # Note! not using the import as this confuses nuke's calback system
        # (several of the key scene callbacks are in the main init file...)
        import tk_nuke
        
        # Make sure callbacks tracking the context switching are active.
        tk_nuke.tank_ensure_callbacks_registered()

    def post_app_init(self):
        """
        Called when all apps have initialized.
        """
        # Figure out what our menu will be named.
        menu_name = "Shotgun"
        if self.get_setting("use_sgtk_as_menu_name", False):
            menu_name = "Sgtk"

        # We have some mode-specific initialization to do.
        if self.hiero_enabled:
            self.post_app_init_hiero(menu_name)
        elif self.studio_enabled:
            self.post_app_init_studio(menu_name)

            # We want to run the Nuke init, as well, to load up
            # any gizmos, but we don't want it to be part of the
            # post_app_init_studio method, since we'll also need
            # to call just the gizmo stuff on context changes and
            # not the other Nuke Studio-related init stuff.
            self.post_app_init_nuke(menu_name)
        else:
            self.post_app_init_nuke(menu_name)

    def post_app_init_studio(self, menu_name="Shotgun"):
        """
        The Nuke Studio specific portion of the engine's post-init process.

        :param menu_name:   The label/name of the menu to be created.
        """
        if self.has_ui:
            # Note! not using the import as this confuses Nuke's callback system
            # (several of the key scene callbacks are in the main init file).
            import tk_nuke
            import hiero
            from hiero.core import env as hiero_env

            # Create the menu!
            self._menu_generator = tk_nuke.NukeStudioMenuGenerator(self, menu_name)
            self._menu_generator.create_menu()

            hiero.core.events.registerInterest(
                "kAfterNewProjectCreated",
                self.set_project_root,
            )

            hiero.core.events.registerInterest(
                "kAfterProjectLoad",
                self._on_project_load_callback,
            )

            # Then we need to setup our context switcher.
            import tk_nuke
            self._context_switcher = tk_nuke.StudioContextSwitcher(self)

            # On selection change we have to check what was selected and pre-load
            # the context if that environment (ie: shot_step) hasn't already been
            # processed. This ensure that all Nuke gizmos for the target environment
            # will be available.
            hiero.core.events.registerInterest(
                "kSelectionChanged",
                self._handle_studio_selection_change,
            )

            try:
                hiero_ver_str = "%s.%s%s" % (
                    hiero_env["VersionMajor"],
                    hiero_env["VersionMinor"],
                    hiero_env["VersionRelease"],
                )
                self.log_user_attribute_metric("Nuke Studio version", hiero_ver_str)
            except:
                # ignore all errors. ex: using a core that doesn't support metrics
                pass

    def post_app_init_hiero(self, menu_name="Shotgun"):
        """
        The Hiero-specific portion of the engine's post-init process.

        :param menu_name:   The label/name of the menu to be created.
        """
        if self.has_ui:
            # Note! not using the import as this confuses Nuke's callback system
            # (several of the key scene callbacks are in the main init file).
            import tk_nuke
            import hiero

            # Create the menu!
            self._menu_generator = tk_nuke.HieroMenuGenerator(self, menu_name)
            self._menu_generator.create_menu()

            hiero.core.events.registerInterest(
                "kAfterNewProjectCreated",
                self.set_project_root,
            )

            hiero.core.events.registerInterest(
                "kAfterProjectLoad",
                self._on_project_load_callback,
            )

            try:
                hiero_ver_str = "%s.%s%s" % (
                    hiero_env["VersionMajor"],
                    hiero_env["VersionMinor"],
                    hiero_env["VersionRelease"],
                )
                self.log_user_attribute_metric("Hiero version", hiero_ver_str)
            except:
                # ignore all errors. ex: using a core that doesn't support metrics
                pass

    def post_app_init_nuke(self, menu_name="Shotgun"):
        """
        The Nuke-specific portion of the engine's post-init process.

        :param menu_name:   The label/name of the menu to be created.
        """

        if self.has_ui and not self.studio_enabled:
            # Note! not using the import as this confuses Nuke's callback system
            # (several of the key scene callbacks are in the main init file).
            import tk_nuke

            # Create the menu!
            self._menu_generator = tk_nuke.NukeMenuGenerator(self, menu_name)
            self._menu_generator.create_menu()

            # Initialize favourite dirs in the file open/file save dialogs
            self.__setup_favorite_dirs()
            
            # Register all panels with nuke's callback system
            # this will be used at nuke startup in order
            # for nuke to be able to restore panels 
            # automatically. For all panels that exist as
            # part of saved layouts, nuke will look through
            # a global list of registered panels, try to locate
            # the one it needs and then run the callback.
            for (panel_id, panel_dict) in self.panels.iteritems():
                nukescripts.panels.registerPanel(
                    panel_id,
                    panel_dict["callback"],
                )

        # Iterate over all apps, if there is a gizmo folder, add it to nuke path.
        for app in self.apps.values():
            # Add gizmos to nuke path.
            app_gizmo_folder = os.path.join(app.disk_location, "gizmos")
            if os.path.exists(app_gizmo_folder):
                # Now translate the path so that nuke is happy on Windows.
                app_gizmo_folder = app_gizmo_folder.replace(os.path.sep, "/")
                self.log_debug("Gizmos found - Adding %s to nuke.pluginAddPath() and NUKE_PATH" % app_gizmo_folder)
                nuke.pluginAddPath(app_gizmo_folder)
                # And also add it to the plugin path - this is so that any 
                # new processes spawned from this one will have access too.
                # (for example if you do file->open or file->new)
                tank.util.append_path_to_env_var("NUKE_PATH", app_gizmo_folder)

        try:
            self.log_user_attribute_metric("Nuke version",
                nuke.env.get("NukeVersionString"))
        except:
            # ignore all errors. ex: using a core that doesn't support metrics
            pass

    def destroy_engine(self):
        """
        Runs when the engine is unloaded, typically at context switch.
        """
        self.log_debug("%s: Destroying..." % self)

        if self._context_switcher:
            self._context_switcher.destroy()

        if self.has_ui:
            self._menu_generator.destroy_menu()

        if self.hiero_enabled or self.studio_enabled:
            import hiero.core

            hiero.core.events.unregisterInterest(
                "kAfterNewProjectCreated",
                self.set_project_root,
            )
            hiero.core.events.unregisterInterest(
                "kAfterProjectLoad",
                self._on_project_load_callback,
            )

            if self.studio_enabled:
                hiero.core.events.unregisterInterest(
                    "kSelectionChanged",
                    self._handle_studio_selection_change,
                )

    def post_context_change(self, old_context, new_context):
        """
        Handles post-context-change requirements for Nuke, Hiero, and Nuke Studio.

        :param old_context: The sgtk.context.Context being switched away from.
        :param new_context: The sgtk.context.Context being switched to.
        """
        self.log_debug("tk-nuke context changed to %s" % str(new_context))

        # We also need to run the post init for Nuke, which will handle
        # getting any gizmos setup.
        if not self.hiero_enabled:
            self.post_app_init_nuke()

        if self._context_change_menu_rebuild:
            self.menu_generator.create_menu()

    #####################################################################################
    # Logging

    def log_debug(self, msg):
        if self.get_setting("debug_logging", False):
            msg = "Shotgun Debug: %s" % msg
            # We will log it via the API, as well as print normally,
            # which should make its way to the scripting console.
            if self.hiero_enabled:
                import hiero
                hiero.core.log.setLogLevel(hiero.core.log.kDebug)
                hiero.core.log.debug(msg)
            print msg

    def log_info(self, msg):
        msg = "Shotgun Info: %s" % msg
        # We will log it via the API, as well as print normally,
        # which should make its way to the scripting console.
        if self.hiero_enabled:
            # NOTE! By default, info logging is turned OFF in hiero
            # meaning that no info messages (nor warning, since they use info to output too)
            # will be output in the console.
            # 
            # In order to have these emitted, we would need to turn them on by doing a 
            # hiero.core.log.setLogLevel(hiero.core.log.kInfo)
            #
            # However this has call been omitted on purpose because too much output 
            # from hiero to stdout/stderr is causing problems with the browser plugin
            # causing it to hang or crash. By keeping the info and warning logging off
            # we are avoiding such hangs and working around this known issue.
            import hiero
            hiero.core.log.info(msg)
        print msg

    def log_warning(self, msg):
        msg = "Shotgun Warning: %s" % msg
        # We will log it via the API, as well as print normally,
        # which should make its way to the scripting console.
        if self.hiero_enabled:
            import hiero
            hiero.core.log.info(msg)
        else:
            nuke.warning(msg)
        print msg

    def log_error(self, msg):
        msg = "Shotgun Error: %s" % msg
        # We will log it via the API, as well as print normally,
        # which should make its way to the scripting console.
        if self.hiero_enabled:
            import hiero
            hiero.core.log.error(msg)
        else:
            nuke.error(msg)
        print msg

    #####################################################################################
    # Panel Support

    def show_panel(self, panel_id, title, bundle, widget_class, *args, **kwargs):
        """
        Shows a panel in Nuke. If the panel already exists, the previous panel is swapped out
        and replaced with a new one. In this case, the contents of the panel (e.g. the toolkit app)
        is not destroyed but carried over to the new panel.
        
        If this is being called from a non-pane menu in Nuke, there isn't a well established logic
        for where the panel should be mounted. In this case, the code will look for suitable
        areas in the UI and try to panel it there, starting by looking for the property pane and
        trying to dock panels next to this.
        
        :param panel_id: Unique id to associate with the panel - normally this is a string obtained
                         via the register_panel() call.
        :param title: The title of the window
        :param bundle: The app, engine or framework object that is associated with this window
        :param widget_class: The class of the UI to be constructed. This must derive from QWidget.
        
        Additional parameters specified will be passed through to the widget_class constructor.
        """
        if self.hiero_enabled:
            self.log_info(
                "Panels are not supported in Hiero. Launching as a dialog..."
            )
            return self.show_dialog(
                title,
                bundle,
                widget_class,
                *args,
                **kwargs
            )

        # Note! Not using the import_module call as this confuses nuke's callback system
        import tk_nuke_qt
        
        # Create the panel.
        panel_widget = tk_nuke_qt.NukePanelWidget(
            bundle,
            title,
            panel_id,
            widget_class,
            *args, **kwargs
        )
        
        if hasattr(tank, "_callback_from_non_pane_menu"):
            # This global flag is set by the menu callback system
            # to indicate that the click comes from a non-pane context.
            # 
            # In this case, we have to figure out where the pane should be shown.
            # Try to parent it next to the properties panel
            # if possible, because this is typically laid out like a classic
            # panel UI - narrow and tall. If not possible, then fall back on other
            # built-in objects and use these to find a location.
            #
            # Note: on Nuke versions prior to 9, a pane is required for the UI to appear.
            built_in_tabs = [
                "Properties.1", # properties dialog - best choice to parent next to
                "DAG.1",        # node graph, so usually wide not tall
                "DopeSheet.1",  # dope sheet, usually wide, not tall
                "Viewer.1",     # viewer
                "Toolbar.1",    # nodes toolbar
            ]
            
            existing_pane = None
            for tab_name in built_in_tabs:
                self.log_debug("Parenting panel - looking for %s tab..." % tab_name)
                existing_pane = nuke.getPaneFor(tab_name)
                if existing_pane:
                    break
    
            if existing_pane is None and nuke.env.get("NukeVersionMajor") < 9:
                # Couldn't find anything to parent next to!
                # Nuke 9 will automatically handle this situation
                # but older versions will not show the UI!
                # Tell the user that they need to have the property
                # pane present in the UI.
                nuke.message("Cannot find any of the standard Nuke UI panels to anchor against. "
                             "Please add a Properties Bin to your Nuke UI layout and try again.")
                return
    
            # All good - we are running nuke 9 and/or 
            # have existing panes to parent against.
            panel_widget.addToPane(existing_pane)   
        else:
            # We are either calling this from a pane restore
            # callback or from the pane menu in Nuke. In both
            # these cases, the current pane is already established
            # by the system, so just add our widget.
            # Add it to the current pane
            panel_widget.addToPane()
        return panel_widget

    #####################################################################################
    # Menu Utilities

    def get_menu_selection(self):
        """
        Returns the list of hiero objects selected in the most recent menu click.
        This list may contain items of various types. To see exactly what is being 
        returned by which methods, turn on debug logging - this will print out details
        of what is going on.
        
        Examples of types that are being returned are:
        
        Selecting a project in the bin view:
        http://docs.thefoundry.co.uk/hiero/10/hieropythondevguide/api/api_core.html#hiero.core.Bin
        
        Selecting an item in a bin view:
        http://docs.thefoundry.co.uk/hiero/10/hieropythondevguide/api/api_core.html#hiero.core.BinItem
        
        Selecting a track:
        http://docs.thefoundry.co.uk/hiero/10/hieropythondevguide/api/api_core.html#hiero.core.TrackItem
        """
        return self._last_clicked_selection
        
    def get_menu_category(self):
        """
        Returns the UI area where the last menu click took place.
        
        Returns one of the following constants:
        
        - HieroEngine.HIERO_BIN_AREA
        - HieroEngine.HIERO_SPREADSHEET_AREA
        - HieroEngine.HIERO_TIMELINE_AREA
        - None for unknown or undefined
        """
        return self._last_clicked_area

    #####################################################################################
    # General Utilities

    def set_project_root(self, event):
        """
        Ensure any new projects get the project root or default startup 
        projects get the project root set properly.

        :param event:   A Nuke event object. It is a standard argument for
                        event callbacks in Nuke, which is what this method is registered
                        as on engine initialization.
        """
        import hiero
        for p in hiero.core.projects():
            if not p.projectRoot():
                self.log_debug(
                    "Setting projectRoot on %s to: %s" % (
                        p.name(),
                        self.tank.project_path
                    )
                )
                p.setProjectRoot(self.tank.project_path)

    def _get_dialog_parent(self):
        """
        Return the QWidget parent for all dialogs created through
        show_dialog and show_modal.
        """
        # See https://github.com/shotgunsoftware/tk-nuke/commit/35ca540d152cc5357dc7e347b5efc728a3a89f4a 
        # for more info. There have been instability issues with nuke 7 causing
        # various crashes, so window parenting on Nuke versions above 6 is
        # currently disabled.
        if nuke.env.get("NukeVersionMajor") == 7:
            return None
        return super(NukeEngine, self)._get_dialog_parent()

    def _handle_studio_selection_change(self, event):
        """
        An event handler that processes selection-change events in Nuke Studio.

        :param event:   The event that triggered this callback's execution.
        """
        # Keep a copy of the current context since we'll need
        # to get back to it after pre-loading the target.
        current_context = self.context
        sender = event.sender
        import hiero

        try:
            for item in sender.selection():
                # Depending on whether this is a BinItem or something
                # else, we have different ways of getting to the Clip
                # object for the item.
                try:
                    clip = item.source()
                except AttributeError:
                    clip = item.activeItem()

                if isinstance(clip, hiero.core.Clip):
                    media = clip.mediaSource()
                    infos = media.fileinfos()
                    file_path = str(infos[0].filename())

                    # If we've already seen this file selected before, or if it's
                    # not a .nk file, then we don't need to do anything.
                    if file_path not in self._processed_paths and file_path.endswith(".nk"):
                        self._processed_paths.append(file_path)
                        self._context_change_menu_rebuild = False
                        current_context = self.context
                        target_context = self._context_switcher.get_new_context(file_path)

                        if target_context:
                            # If this environment has already been processed then
                            # we don't need to do anything. There's only one "shot_step"
                            # environment out there, regardless of what .nk file was
                            # selected.
                            env_name = target_context.tank.execute_core_hook(
                                tank.constants.PICK_ENVIRONMENT_CORE_HOOK_NAME,
                                context=target_context,
                            )

                            if env_name not in self._processed_environments:
                                self._processed_environments.append(env_name)
                                self._context_switcher.change_context(target_context)
        except Exception, e:
            # If anything went wrong, we can just let the finally block
            # run, which will put things back to the way they were.
            self.log_debug("Unable to pre-load environment: %s" % str(e))
        finally:
            # If the context was changed during the course of the handling
            # of the selection event, we need to go back to what we had.
            # Once we do we can then make sure that we re-enable menu rebuilds
            # for future context changes.
            if self.context is not current_context:
                self._context_switcher.change_context(current_context)
            self._context_change_menu_rebuild = True

    def _on_project_load_callback(self, event):
        """
        Callback executed after project load in Hiero and Nuke Studio. This
        triggers an attempt to change the SGTK context to that of the newly
        opened project file.

        :param event:   The event object from Hiero/NS.
        """
        import hiero.core

        project = hiero.core.projects()[-1]
        script_path = project.path()

        # We're going to just skip doing anything if this fails
        # for any reason. It would be nice to swap to the error
        # menu item, but unfortunately a project open event is
        # triggered on launch when Hiero/Nuke Studio loads the
        # "Untitled" project from the Nuke install location. There
        # isn't a way to distinguish between that and something the
        # user purposefully opened, and we don't want to hose the
        # toolkit context with that.
        try:
            tk = tank.tank_from_path(script_path)

            # Extract a new context based on the file and change to that
            # context.
            new_context = tk.context_from_path(
                script_path,
                previous_context=self.context,
            )

            if new_context != self.context:
                tank.platform.change_context(new_context)
        except Exception:
            self.log_debug("Unable to determine context for file: %s" % script_path)
    
    def __setup_favorite_dirs(self):
        """
        Sets up nuke shortcut "favorite dirs" that are presented in the left hand side of 
        Nuke common dialogs (open, save).

        Nuke currently only writes favorites to disk in ~/.nuke/folders.nk. If you add/remove 
        one in the UI. Doing them via the api only updates them for the session (Nuke bug #3740). 
        See http://forums.thefoundry.co.uk/phpBB2/viewtopic.php?t=3481&start=15
        """
        engine_root_dir = self.disk_location
        sg_logo = os.path.abspath(os.path.join(engine_root_dir, "resources", "sg_logo_80px.png"))

        # Ensure old favorites we used to use are removed. 
        supported_entity_types = ["Shot", "Sequence", "Scene", "Asset", "Project"]
        for x in supported_entity_types:
            nuke.removeFavoriteDir("Tank Current %s" % x)
        nuke.removeFavoriteDir("Tank Current Work")
        nuke.removeFavoriteDir("Shotgun Current Project")
        nuke.removeFavoriteDir("Shotgun Current Work")

        # Add favorties for current project root(s).
        proj = self.context.project
        current_proj_fav = self.get_setting("project_favourite_name")
        # Only add these current project entries if we have a value from settings.
        # Otherwise, they have opted to not show them.
        if proj and current_proj_fav:
            proj_roots = self.tank.roots
            for root_name, root_path in proj_roots.items():
                dir_name = current_proj_fav
                if len(proj_roots) > 1:
                    dir_name += " (%s)" % root_name

                # Remove old directory
                nuke.removeFavoriteDir(dir_name)

                # Add new path
                nuke.addFavoriteDir(dir_name, 
                                    directory=root_path,  
                                    type=(nuke.IMAGE|nuke.SCRIPT|nuke.GEO), 
                                    icon=sg_logo, 
                                    tooltip=root_path)

        # Add favorites directories from the config
        for favorite in self.get_setting("favourite_directories"):
            # Remove old directory
            nuke.removeFavoriteDir(favorite['display_name'])
            try:
                template = self.get_template_by_name(favorite['template_directory'])
                fields = self.context.as_template_fields(template)
                path = template.apply_fields(fields)
            except Exception, e:
                msg = "Error processing template '%s' to add to favorite " \
                      "directories: %s" % (favorite['template_directory'], e)
                self.log_exception(msg)
                continue

            # Add new directory 
            icon_path = favorite.get('icon')
            if not os.path.isfile(icon_path) or not os.path.exists(icon_path):
                icon_path = sg_logo

            nuke.addFavoriteDir(favorite['display_name'], 
                                directory=path,  
                                type=(nuke.IMAGE|nuke.SCRIPT|nuke.GEO), 
                                icon=icon_path, 
                                tooltip=path)
        
