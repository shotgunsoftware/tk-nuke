"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

A Nuke engine for Tank.

"""

import tank
import platform
import time
import nuke
import os
import threading
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
        else:
            print("TANK_PROGRESS Task:%s Progress:%d%%" % (self.__title, percent))
    
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
        if self.context.entity:
            # context has an entity
            locations = self.tank.paths_from_entity(self.context.entity["type"], 
                                                    self.context.entity["id"])
        elif self.context.project:
            # context has a project
            locations = self.tank.paths_from_entity(self.context.project["type"], 
                                                    self.context.project["id"])
        else:
            # must have at least a project in the context to even start!
            raise tank.TankError("The nuke engine needs at least a project in the context "
                                 "in order to start! Your context: %s" % self.context)
        
        # make sure there are folders on disk
        if len(locations) == 0:
            raise tank.TankError("No folders on disk are associated with the current context. The Nuke "
                            "engine requires a context which exists on disk in order to run "
                            "correctly.")
        
        # make sure we are not running that bloody nuke PLE!
        if nuke.env.get("ple") == True:
            self.log_error("The Nuke Engine does not work with the Nuke PLE!")
            return
        
        # make sure that nuke has a higher version than 6.3v5
        # this is because of pyside
        if nuke.env.get("NukeVersionMajor") < 6:
            self.log_error("Tank Requires at least Nuke 6.3v5!")
            return
        if nuke.env.get("NukeVersionMajor") == 6 and \
           nuke.env.get("NukeVersionMinor") < 3:
            self.log_error("Tank Requires at least Nuke 6.3v5!")
            return
        if nuke.env.get("NukeVersionMajor") == 6 and \
           nuke.env.get("NukeVersionMinor") == 3 and \
           nuke.env.get("NukeVersionRelease") < 5:
            self.log_error("Tank Requires at least Nuke 6.3v5!")
            return
                    
        # keep track of if a UI exists
        self._ui_enabled = nuke.env.get("gui")
        
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

            self._menu_generator = tk_nuke.MenuGenerator(self)
            self._menu_generator.create_menu()
            self.__setup_favourite_dirs()
            
        # iterate over all apps, if there is a gizmo folder, add it to nuke path
        for app in self.apps.values():
            # add gizmo to nuke path
            app_gizmo_folder = os.path.join(app.disk_location, "gizmos")
            if os.path.exists(app_gizmo_folder):
                self.log_debug("Adding %s to nuke node path" % app_gizmo_folder)
                nuke.pluginAddPath(app_gizmo_folder)
                # and also add it to the plugin path - this is so that any 
                # new processes spawned from this one will have access too.
                # (for example if you do file->open or file->new)
                tank.util.append_path_to_env_var("NUKE_PATH", app_gizmo_folder)
            
        
       
    def destroy_engine(self):
        self.log_debug("%s: Destroying..." % self)
        if self._ui_enabled:
            self._menu_generator.destroy_menu()

    ##########################################################################################
    # logging interfaces
    
    def log_debug(self, msg):
        if self.get_setting("debug_logging", False):
            # print it in the console
            msg = "Tank Debug: %s" % msg
            print msg

    def log_info(self, msg):
        msg = "Tank Info: %s" % msg
        # print it in the console
        print msg
        
    def log_warning(self, msg):
        msg = "Tank Warning: %s" % msg
        # print it in the nuke error console
        nuke.warning(msg)
        # also print it in the nuke script console
        print msg
    
    def log_error(self, msg):
        msg = "Tank Error: %s" % msg
        
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
        
        supported_entity_types = ["Shot", "Sequence", "Scene", "Asset", "Project"]
        
        # remove all previous favs
        for x in supported_entity_types:
            nuke.removeFavoriteDir("Tank Current %s" % x)
        
        # get a list of project entities to process
        entities = []
        if self.context.entity:
            # current entity
            entities.append(self.context.entity)
        if self.context.project:
            # current proj
            entities.append(self.context.project)
        
        for x in entities:
            sg_et = x["type"]
            if sg_et not in supported_entity_types:
                # don't know how to remove this, so don't add it!
                continue
            
            paths = self.tank.paths_from_entity(x["type"], x["id"])
            if len(paths) > 0:
                # for now just pick the first path associated with this entity
                # todo: later on present multiple ones? or decide on a single path to choose?
                path = paths[0]
                nuke.addFavoriteDir("Tank Current %s" % sg_et, 
                                    directory=path,  
                                    type=(nuke.IMAGE|nuke.SCRIPT|nuke.FONT|nuke.GEO), 
                                    icon=tank_logo_small, 
                                    tooltip=path)
        
    ##########################################################################################
    # queue

    def add_to_queue(self, name, method, args):
        """
        Nuke implementation of the engine synchronous queue. Adds an item to the queue.
        """
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
        nuke.executeInMainThread(self._current_queue_item["progress"].set_progress, percent)
    
    def execute_queue(self):
        """
        Executes all items in the queue, one by one, in a controlled fashion
        """
        if self._queue_running:
            self.log_warning("Cannot execute queue - it is already executing!")
            return
        self._queue_running = True
        
        # create progress items for all queue items
        for x in self._queue:
            x["progress"] = TankProgressWrapper(x["name"], self._ui_enabled)

        threading.Thread( target=self.__execute_queue).start()  

        
    def __execute_queue(self):
        """
        Runs in a separate thread.
        """

        # execute one after the other syncronously
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
                print msg
                # FOOBAR - Nuke seems to ignore this call. WTF? FAIL
                nuke.executeInMainThread(self.log_exception, msg)
            finally:
                nuke.executeInMainThread(self._current_queue_item["progress"].close)
                # nuke needs time to GC I think...
                time.sleep(0.2)

        # done
        self._queue_running = False
            
        
            
            
