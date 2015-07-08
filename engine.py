# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
A Nuke engine for Tank.
"""

import tank
import platform
import time
import nuke
import os
import re
import traceback
import unicodedata
import nukescripts
from tank_vendor import yaml

class NukeEngine(tank.platform.Engine):

    ##########################################################################################
    # init
    
    def init_engine(self):
        """
        Called at Engine startup
        """
        
        self.log_debug("%s: Initializing..." % self)

        # track the panels that apps have registered with the engine 
        self._panels = {}

        # now check that there is a location on disk which corresponds to the context
        if self.context.project is None:
            # must have at least a project in the context to even start!
            raise tank.TankError("The nuke engine needs at least a project in the context "
                                 "in order to start! Your context: %s" % self.context)
                
        # make sure we are not running that bloody nuke PLE!
        if nuke.env.get("ple") == True:
            self.log_error("The Nuke Engine does not work with the Nuke PLE!")
            return
        
        # make sure that nuke has a higher version than 6.3v5
        # this is because of pyside
        nuke_version = (nuke.env.get("NukeVersionMajor"), nuke.env.get("NukeVersionMinor"), nuke.env.get("NukeVersionRelease"))
        
        if nuke_version[0] < 6:
            self.log_error("Nuke 6.3v5 is the minimum version supported!")
            return
        elif (nuke_version[0] == 6
              and nuke_version[1] < 3):
            self.log_error("Nuke 6.3v5 is the minimum version supported!")
            return
        elif (nuke_version[0] == 6
              and nuke_version[1] == 3
              and nuke_version[2] < 5):
            self.log_error("Nuke 6.3v5 is the minimum version supported!")
            return
        
        # keep track of if a UI exists
        self._ui_enabled = nuke.env.get("gui")

        # versions > 9.0 have not yet been tested so show a message to that effect:
        if nuke_version[0] > 9 or (nuke_version[0] == 9 and nuke_version[1] > 0):
            # this is an untested version of Nuke
            msg = ("The Shotgun Pipeline Toolkit has not yet been fully tested with Nuke %d.%dv%d. "
                   "You can continue to use the Toolkit but you may experience bugs or "
                   "instability.  Please report any issues you see to toolkitsupport@shotgunsoftware.com" 
                   % (nuke_version[0], nuke_version[1], nuke_version[2]))
            
            # show nuke message if in UI mode, this is the first time the engine has been started
            # and the warning dialog isn't overriden by the config:
            if (self._ui_enabled 
                and not "TANK_NUKE_ENGINE_INIT_NAME" in os.environ
                and nuke_version[0] >= self.get_setting("compatibility_dialog_min_version", 10)):
                nuke.message("Warning - Shotgun Pipeline Toolkit!\n\n%s" % msg)
                           
            # and log the warning
            self.log_warning(msg)
            
        # now prepare tank so that it will be picked up by any new processes
        # created by file->new or file->open.
            
        # Store data needed for bootstrapping Tank in env vars. Used in startup/menu.py
        os.environ["TANK_NUKE_ENGINE_INIT_NAME"] = self.instance_name
        os.environ["TANK_NUKE_ENGINE_INIT_CONTEXT"] = yaml.dump(self.context)
        os.environ["TANK_NUKE_ENGINE_INIT_PROJECT_ROOT"] = self.tank.project_path
        
        # add our startup path to the nuke init path
        startup_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "startup"))
        tank.util.append_path_to_env_var("NUKE_PATH", startup_path)        
    
        # we also need to pass the path to the python folder down to the init script
        # because nuke python does not have a __file__ attribute for that file
        local_python_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "python"))
        os.environ["TANK_NUKE_ENGINE_MOD_PATH"] = local_python_path
        
    
    def pre_app_init(self):
        """
        Called at startup, but after QT has been initialized
        """
        # note! not using the import as this confuses nuke's calback system
        # (several of the key scene callbacks are in the main init file...)
        import tk_nuke
        
        # make sure callbacks tracking the context switching are active
        tk_nuke.tank_ensure_callbacks_registered()
        
       
    def post_app_init(self):
        """
        Called when all apps have initialized
        """
        # render the menu!
        if self._ui_enabled:
            
            # note! not using the import as this confuses nuke's calback system
            # (several of the key scene callbacks are in the main init file...)            
            import tk_nuke

            menu_name = "Shotgun"
            if self.get_setting("use_sgtk_as_menu_name", False):
                menu_name = "Sgtk"
            
            # create menu
            self._menu_generator = tk_nuke.MenuGenerator(self, menu_name)
            self._menu_generator.create_menu()
            
            # initialize favourite dirs in the file open/file save dialogs
            self.__setup_favorite_dirs()
            
        # iterate over all apps, if there is a gizmo folder, add it to nuke path
        for app in self.apps.values():
            # add gizmo to nuke path
            app_gizmo_folder = os.path.join(app.disk_location, "gizmos")
            if os.path.exists(app_gizmo_folder):
                # now translate the path so that nuke is happy on windows
                app_gizmo_folder = app_gizmo_folder.replace(os.path.sep, "/")
                self.log_debug("Gizmos found - Adding %s to nuke.pluginAddPath() and NUKE_PATH" % app_gizmo_folder)
                nuke.pluginAddPath(app_gizmo_folder)
                # and also add it to the plugin path - this is so that any 
                # new processes spawned from this one will have access too.
                # (for example if you do file->open or file->new)
                tank.util.append_path_to_env_var("NUKE_PATH", app_gizmo_folder)
                   
    def destroy_engine(self):
        """
        Runs when the engine is unloaded, e.g. typically at context switch.
        """
        self.log_debug("%s: Destroying..." % self)
        if self._ui_enabled:
            self._menu_generator.destroy_menu()
        

    @property
    def has_ui(self):
        """
        Detect and return if nuke is running in batch mode
        """
        return self._ui_enabled

    def _get_dialog_parent(self):
        """
        Return the QWidget parent for all dialogs created through show_dialog & show_modal.
        """
        # see https://github.com/shotgunsoftware/tk-nuke/commit/35ca540d152cc5357dc7e347b5efc728a3a89f4a 
        # for more info. There have been instability issues with nuke 7 causing various crashes, so 
        # window parenting on Nuke versions above 6 is currently disabled.
        if nuke.env.get("NukeVersionMajor") > 6:
            return None
        return super(NukeEngine, self)._get_dialog_parent()

    ##########################################################################################
    # logging interfaces
    
    def log_debug(self, msg):
        if self.get_setting("debug_logging", False):
            # print it in the console
            msg = "Shotgun Debug: %s" % msg
            print msg

    def log_info(self, msg):
        msg = "Shotgun Info: %s" % msg
        # print it in the console
        print msg
        
    def log_warning(self, msg):
        msg = "Shotgun Warning: %s" % msg
        # print it in the nuke error console
        nuke.warning(msg)
        # also print it in the nuke script console
        print msg
    
    def log_error(self, msg):
        msg = "Shotgun Error: %s" % msg        
        # print it in the nuke error console
        nuke.error(msg)
        # also print it in the nuke script console
        print msg        
        
    
    ##########################################################################################
    # panel interfaces
    
    def _generate_panel_id(self, dialog_name, bundle):
        """
        Given a dialog name and a bundle, generate a Nuke panel id.
        This panel id is used by Nuke to identify and persist the panel.
        
        This will return something like 'shotgun_tk_multi_loader2_main'
        
        :param dialog_name: An identifier string to identify the dialog to be hosted by the panel
        :param bundle: The bundle (e.g. app) object to be associated with the panel
        :returns: a unique identifier string 
        """
        panel_id = "shotgun_%s_%s" % (bundle.name, dialog_name)
        # replace any non-alphanumeric chars with underscores
        panel_id = re.sub("\W", "_", panel_id)
        panel_id = panel_id.lower()
        self.log_debug("Unique panel id for %s %s -> %s" % (bundle, dialog_name, panel_id))
        return panel_id 
        
    def _panel_factory_callback(self, panel_id):
        """
        Given a panel id, generate a panel UI.
        
        This method is intended to be executed by nuke itself as a callback
        that runs when panels are being restored, either at startup or 
        at UI profile switch.
        
        :param panel_id: Unique identifier string for the panel
        """
        # note: Nuke silently consumes any exceptions within the callback system
        # so add a catch all exception handler around this to make sure
        # we properly log any output 
        try:
            # note! not using the import as this confuses nuke's calback system 
            import tk_nuke
        
            self.log_debug("Panel Factory Callback: Generating UI for panel id '%s'." % panel_id)
            
            # the callback is registered at the same time as the panel callback,
            # so we can assume that our _panels lookup data structure has a matching
            # object present
            panel = self._panels[panel_id]
            # create a new panel widget
            panel_widget = tk_nuke.NukePanelWidget(panel["bundle"],
                                                   panel["title"], 
                                                   panel_id, 
                                                   panel["widget_class"],
                                                   *panel["args"],
                                                   **panel["kwargs"])
            # and add it to the current pane context (nuke handles this state)
            panel_widget.addToPane()
            
            return panel_widget
            
        except Exception, e:
            # catch-em-all here because otherwise Nuke will just silently swallow them
            self.log_exception("Could not generate panel UI for panel id '%s'" % panel_id)
        
        
    def register_panel(self, title, bundle, widget_class, *args, **kwargs):
        """
        Similar to register_command, but instead of registering a menu item in the form of a
        command, this method registers a UI panel. The arguments passed to this method is the
        same as for show_panel().
        
        Just like with the register_command() method, panel registration should be executed 
        from within the init phase of the app. Once a panel has been registered, it is possible
        for the engine to correctly restore panel UIs that persist between sessions. 
        
        Not all engines support this feature, but in for example Nuke, a panel can be saved in 
        a saved layout. Apps wanting to be able to take advantage of the persistance given by
        these saved layouts will need to call register_panel as part of their init_app phase.
        
        In order to show or focus on a panel, use the show_panel() method instead.
        
        :param title: The title of the window
        :param bundle: The app, engine or framework object that is associated with this panel
        :param widget_class: The class of the UI to be constructed. This must derive from QWidget.
        
        Additional parameters specified will be passed through to the widget_class constructor.
        """
        # generate unique identifier
        panel_id = self._generate_panel_id(title, bundle)
        
        # track registered panels
        self.log_debug("Registering panel '%s'" % panel_id)
        self._panels[panel_id] = {"title": title, 
                                  "bundle": bundle, 
                                  "widget_class": widget_class,
                                  "args": args,
                                  "kwargs": kwargs}

        # tell nuke how to create this panel
        # this will be used at nuke startup in order
        # for nuke to be able to restore panels 
        # automatically. For all panels that exist as
        # part of saved layouts, nuke will look through
        # a global list of registered panels, try to locate
        # the one it needs and then run the callback         
        fn = lambda : self._panel_factory_callback(panel_id)
        nukescripts.panels.registerPanel(panel_id, fn)
                   
        
    def show_panel(self, title, bundle, widget_class, *args, **kwargs):
        """
        Shows a panel in a way suitable for this engine. The engine will attempt to
        integrate it as seamlessly as possible into the host application. If the engine does 
        not specifically implement panel support, the window will be shown as a modeless
        dialog instead.
        
        :param title: The title of the window
        :param bundle: The app, engine or framework object that is associated with this window
        :param widget_class: The class of the UI to be constructed. This must derive from QWidget.
        
        Additional parameters specified will be passed through to the widget_class constructor.
        """
        # note! not using the import as this confuses nuke's calback system
        # (several of the key scene callbacks are in the main init file...)
        import tk_nuke
        
        # now look for the tank._panel_callback_from_pane_menu property
        # if this exists, that is an indication that this call comes from 
        # within a nuke pane menu (see menu generation module). In this case,
        # the correct pane to place the UI in is picked up automatically
        # by the addToPane() method. 
        #
        # When this is not called from within a panel, we instead need to 
        # find a suitable place to mount it. 
        try:
            pane_callback = tank._panel_callback_from_pane_menu
        except AttributeError:
            pane_callback = False
                
        # create the panel
        panel_id = self._generate_panel_id(title, bundle)
        panel_widget = tk_nuke.NukePanelWidget(bundle, title, panel_id, widget_class, *args, **kwargs)
        
        if pane_callback:
            # add it to the current pane
            panel_widget.addToPane()
            
        else:
        
            # parent it. Try to parent it next to the properties panel
            # if possible, because this is typically laid out like a classic
            # panel UI - narrow and tall. If not possible, then fall back on other
            # built-in objects and use these to find a location.
            #
            # Note: on nuke versions prior to 9, a pane is required for the UI to appear.
            
            built_in_tabs = ["Properties.1",   # properties dialog - best choice to parent next to
                             "DAG.1",          # node graph, so usually wide not tall
                             "DopeSheet.1",    # dope sheet, usually wide, not tall
                             "Viewer.1",       # viewer
                             "Toolbar.1"]      # nodes toolbar
            
            existing_pane = None
            for tab_name in built_in_tabs:
                self.log_debug("Parenting panel - looking for %s tab..." % tab_name)
                existing_pane = nuke.getPaneFor(tab_name)
                if existing_pane:
                    break
    
            if existing_pane is None and nuke.env.get("NukeVersionMajor") < 9:
                # couldn't find anything to parent next to!
                # nuke 9 will automatically handle this situation
                # but older versions will not show the UI!
                # tell the user that they need to have the property
                # pane present in the UI
                nuke.message("Cannot find any of the standard Nuke UI panels to anchor against. "
                             "Please add a Properties Bin to your Nuke UI layout and try again.")
                return
    
            # ok all good - we are running nuke 9 and/or 
            # have existing panes to parent against.
            panel_widget.addToPane(existing_pane)        
        
    
    ##########################################################################################
    # managing favorite dirs            
    
    def __setup_favorite_dirs(self):
        """
        Sets up nuke shortcut "favorite dirs" that are presented in the left hand side of 
        nuke common dialogs (open, save)

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

        # add favorties for current project root(s)
        proj = self.context.project
        current_proj_fav = self.get_setting("project_favourite_name")
        # only add these current project entries if we have a value from settings.
        # Otherwise, they have opted to not show them.
        if proj and current_proj_fav:
            proj_roots = self.tank.roots
            for root_name, root_path in proj_roots.items():
                dir_name = current_proj_fav
                if len(proj_roots) > 1:
                    dir_name += " (%s)" % root_name

                # remove old directory
                nuke.removeFavoriteDir(dir_name)
            
                # add new path
                nuke.addFavoriteDir(dir_name, 
                                    directory=root_path,  
                                    type=(nuke.IMAGE|nuke.SCRIPT|nuke.GEO), 
                                    icon=sg_logo, 
                                    tooltip=root_path)

        # add favorites directories from the config
        for favorite in self.get_setting("favourite_directories"):
            # remove old directory
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
            
            # add new directory 
            icon_path = favorite.get('icon')
            if not os.path.isfile(icon_path) or not os.path.exists(icon_path):
                icon_path = sg_logo

            nuke.addFavoriteDir(favorite['display_name'], 
                                directory=path,  
                                type=(nuke.IMAGE|nuke.SCRIPT|nuke.GEO), 
                                icon=icon_path, 
                                tooltip=path)
        
