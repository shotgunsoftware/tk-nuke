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
            
            # register all panels with nuke's callback system
            # this will be used at nuke startup in order
            # for nuke to be able to restore panels 
            # automatically. For all panels that exist as
            # part of saved layouts, nuke will look through
            # a global list of registered panels, try to locate
            # the one it needs and then run the callback         
            for (panel_id, panel_dict) in self.panels.iteritems():
                nukescripts.panels.registerPanel(panel_id, panel_dict["callback"])
            
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
        # note! not using the import as this confuses nuke's calback system
        # (several of the key scene callbacks are in the main init file...)
        import tk_nuke
        
        # create the panel
        panel_widget = tk_nuke.NukePanelWidget(bundle, title, panel_id, widget_class, *args, **kwargs)
        
        if hasattr(tank, "_callback_from_non_pane_menu"):
            # this global flag is set by the menu callback system
            # to indicate that the click comes from a non-pane context.
            # 
            # In this case, we have to figure out where the pane should be shown.
            # Try to parent it next to the properties panel
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
        
        else:
            # we are either calling this from a pane restore
            # callback or from the pane menu in Nuke. In both
            # these cases, the current pane is already established
            # by the system, so just add our widget.
            # add it to the current pane
            panel_widget.addToPane()

        
        # return the created widget
        return panel_widget     
        
    
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
        
