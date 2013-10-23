# Copyright (c) 2013 Shotgun Software Inc.
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
import traceback
import unicodedata
from tank_vendor import yaml

import nukescripts

class TankProgressWrapper(object):
    """
    A progressbar wrapper for nuke.
    Does not currently handle the cancel button.
    It is nice to wrap the nuke object like this because otherwise 
    it can be tricky to delete later.
    """
    def __init__(self, title, ui_enabled):
        self.__ui = ui_enabled
        self.__title = title
        if self.__ui:
            self.__p = nuke.ProgressTask(title)
    
    def set_progress(self, percent):
        if self.__ui:
            self.__p.setProgress(percent)
            # since we are running async,
            # give nuke a chance to process its own events 
            time.sleep(0.1)
        else:
            print("SHOTGUN_PROGRESS Task:%s Progress:%d%%" % (self.__title, percent))
    
    def close(self):
        if self.__ui:
            self.__p.setProgress(100)
            self.__p = None

class NukeEngine(tank.platform.Engine):

    ##########################################################################################
    # init
    
    def init_engine(self):
        
        # note! not using the import as this confuses nuke's calback system
        # (several of the key scene callbacks are in the main init file...)
        import tk_nuke
        
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
        if nuke.env.get("NukeVersionMajor") < 6:
            self.log_error("Nuke 6.3v5 is the minimum version supported!")
            return
        if nuke.env.get("NukeVersionMajor") == 6 and \
           nuke.env.get("NukeVersionMinor") < 3:
            self.log_error("Nuke 6.3v5 is the minimum version supported!")
            return
        if nuke.env.get("NukeVersionMajor") == 6 and \
           nuke.env.get("NukeVersionMinor") == 3 and \
           nuke.env.get("NukeVersionRelease") < 5:
            self.log_error("Nuke 6.3v5 is the minimum version supported!")
            return
        
        # keep track of if a UI exists
        self._ui_enabled = nuke.env.get("gui")

        # versions > 7.x have not yet been tested so show a message to that effect:
        if nuke.env.get("NukeVersionMajor") > 7:
            # this is an untested version of Nuke
            msg = ("The Shotgun Pipeline Toolkit has not yet been fully tested with Nuke %d.%dv%d. "
                   "You can continue to use the Toolkit but you may experience bugs or "
                   "instability.  Please report any issues you see to toolkitsupport@shotgunsoftware.com" 
                   % (nuke.env.get("NukeVersionMajor"), nuke.env.get("NukeVersionMinor"), nuke.env.get("NukeVersionRelease")))
            
            # show nuke message if in UI mode and this is the first time the engine has been started:
            if self._ui_enabled and not "TANK_NUKE_ENGINE_INIT_NAME" in os.environ:
                nuke.message("Warning - Shotgun Pipeline Toolkit!\n\n%s" % msg)
                           
            # and log the warning
            self.log_warning(msg)
            
        # create queue
        self._queue = []
        self._queue_running = False
                    
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

            self._menu_generator = tk_nuke.MenuGenerator(self, menu_name)
            self._menu_generator.create_menu()
            self.__setup_favourite_dirs()
            
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
        
        # and pop up UI
        nuke.message(msg)
        
    
    ##########################################################################################
    # managing favourite dirs            
    
    def __setup_favourite_dirs(self):
        """
        Sets up nuke shortcut "favourite dirs"
        that are presented in the left hand side of 
        nuke common dialogs (open, save)
        """
        
        engine_root_dir = self.disk_location
        tank_logo_small = os.path.abspath(os.path.join(engine_root_dir, "resources", "logo_color_16.png"))
        
        # old versions were referring to these favourites - so keep them around to make
        # sure there are no old leftovers in the system...
        supported_entity_types = ["Shot", "Sequence", "Scene", "Asset", "Project"]
        for x in supported_entity_types:
            nuke.removeFavoriteDir("Tank Current %s" % x)

        # new style favourites are simply "Tank Current Project" and "Tank Current Work"
        
        # with the rename, make sure the old 'Tank' directories are removed:
        nuke.removeFavoriteDir("Tank Current Project")
        nuke.removeFavoriteDir("Tank Current Work")
        # and then use the newer, new 'Shotgun' directories:
        nuke.removeFavoriteDir("Shotgun Current Project")
        nuke.removeFavoriteDir("Shotgun Current Work")

        # we only present these shortcuts if there is exactly one path resolving to the work
        # area or the project - otherwise it is just confusing!

        # handle the project
        if self.context.project:
            proj = self.context.project
            paths = self.tank.paths_from_entity(proj["type"], proj["id"])
            if len(paths) == 1:
                p = paths[0]
                nuke.addFavoriteDir("Shotgun Current Project", 
                                    directory=p,  
                                    type=(nuke.IMAGE|nuke.SCRIPT|nuke.GEO), 
                                    icon=tank_logo_small, 
                                    tooltip=p)

        # handle the current work
        paths = self.context.filesystem_locations
        if len(paths) == 1:
            p = paths[0]            
            nuke.addFavoriteDir("Shotgun Current Work", 
                                directory=p,  
                                type=(nuke.IMAGE|nuke.SCRIPT|nuke.GEO), 
                                icon=tank_logo_small, 
                                tooltip=p)
        
    ##########################################################################################
    # queue

    def add_to_queue(self, name, method, args):
        """
        Nuke implementation of the engine synchronous queue. Adds an item to the queue.
        """
        self.log_warning("The Engine Queue is now deprecated! Please contact support@shotgunsoftware.com")
        qi = {}
        qi["name"] = name
        qi["method"] = method
        qi["args"] = args
        self._queue.append(qi)
    
    def report_progress(self, percent):
        """
        Callback function part of the engine queue. This is being passed into the methods
        that are executing in the queue so that they can report progress back if they like
        """
        self._current_queue_item["progress"].set_progress(percent)
    
    def execute_queue(self):
        """
        Executes all items in the queue, one by one, in a controlled fashion
        """
        self.log_warning("The Engine Queue is now deprecated! Please contact support@shotgunsoftware.com")
        if self._queue_running:
            self.log_warning("Cannot execute queue - it is already executing!")
            return
        self._queue_running = True
        
        # create progress items for all queue items
        for x in self._queue:
            x["progress"] = TankProgressWrapper(x["name"], self._ui_enabled)

        # execute one after the other synchronously
        while len(self._queue) > 0:
            
            # take one item off
            self._current_queue_item = self._queue.pop(0)
            
            # process it
            try:
                kwargs = self._current_queue_item["args"]
                # force add a progress_callback arg - this is by convention
                kwargs["progress_callback"] = self.report_progress
                # init progress bar
                self.report_progress(0)
                # execute
                self._current_queue_item["method"](**kwargs)
            except Exception, e:
                # error and continue
                msg = "Error processing callback %s. Error reported: %s" % (self._current_queue_item, e)
                self.log_exception(msg)
            finally:
                self._current_queue_item["progress"].close()
                # nuke needs time to GC I think...
                time.sleep(0.2)

        # done
        self._queue_running = False
            
        
            
            
