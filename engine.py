"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

A Nuke engine for Tank.

"""

import tank
import platform
import nuke
import os
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
            self.__p = None

class NukeEngine(tank.platform.Engine):

    ##########################################################################################
    # init
    
    def init_engine(self):
        
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
        
        # keep track of if a UI exists
        self._ui_enabled = nuke.env.get("gui")
        
        # create queue
        self._queue = []
                    
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
    
        # render the menu!
        if self._ui_enabled:
            self._create_menu()
            self.__setup_favourite_dirs()
        
        # make sure callbacks tracking the context switching are active
        tk_nuke.tank_ensure_callbacks_registered()
        
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
            self._menu_handle.clearMenu()
            self._node_menu_handle.clearMenu()

    ##########################################################################################
    # logging interfaces
    
    def log_debug(self, msg):
        if self.get_setting("debug_logging", False):
            msg = "Tank Debug: %s" % msg
            nuke.debug(msg)

    def log_info(self, msg):
        msg = "Tank Info: %s" % msg
        nuke.debug(msg)

        nuke.debug("Tank: %s" % msg)
        
    def log_warning(self, msg):
        msg = "Tank Warning: %s" % msg
        nuke.warning(msg)
    
    def log_error(self, msg):
        msg = "Tank Error: %s" % msg
        nuke.error(msg)
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
                                    icon=self._tk2_logo_small, 
                                    tooltip=path)
        
    ##########################################################################################
    # managing the menu            
    
    def __add_documentation_item(self, menu, caption, url):
        """
        Helper that adds a single doc item to the menu
        """
        # deal with nuke's inability to handle unicode. #fail
        if url.__class__ == unicode:
            url = unicodedata.normalize('NFKD', url).encode('ascii', 'ignore')
        cmd = "import nukescripts.openurl; nukescripts.openurl.start('%s')" % url
        if caption.__class__ == unicode:
            caption = unicodedata.normalize('NFKD', caption).encode('ascii', 'ignore')
        menu.addCommand(caption, cmd)
    
    def __add_documentation_to_menu(self):
        """
        Adds documentation items to menu based on what docs are available. 
        """
        
        # create Help menu
        self._menu_handle.addSeparator()
        help_menu = self._menu_handle.addMenu("Help")

        if self.documentation_url:
            self.__add_documentation_item(help_menu, "Engine Documentation", self.documentation_url)

        for app in self.apps.values():
            if app.documentation_url:
                self.__add_documentation_item(help_menu, 
                                              "%s Documentation" % app.display_name, 
                                              app.documentation_url)
                
        if self.tank.documentation_url:
            self.__add_documentation_item(help_menu, "Tank Core Documentation", self.tank.documentation_url)

    def __add_context_menu(self):
        """
        Adds a context menu which displays the current context
        """        
        
        ctx = self.context
        
        if ctx.entity is None:
            # project-only!
            ctx_name = "[%s]" % ctx.project["name"]
        
        elif ctx.step is None and ctx.task is None:
            # entity only
            # e.g. [Shot ABC_123]
            ctx_name = "[%s %s]" % (ctx.entity["type"], ctx.entity["name"])

        else:
            # we have either step or task
            task_step = None
            if ctx.step:
                task_step = ctx.step.get("name")
            if ctx.task:
                task_step = ctx.task.get("name")
            
            # e.g. [Lighting, Shot ABC_123]
            ctx_name = "[%s, %s %s]" % (task_step, ctx.entity["type"], ctx.entity["name"])
        
        # create the menu object        
        self._menu_handle.addCommand(ctx_name, self.__show_context_ui)
                        
        # and finally a separator
        self._menu_handle.addSeparator()
    
    def __show_context_ui(self):
        """
        """
        from tk_nuke import ContextDetailsDialog
        # some QT notes here. Need to keep the dialog object from being GC-ed
        # otherwise pyside will go hara kiri. QT has its own loop to track
        # objects and destroy them and unless we store the dialog as a member
        self._dialog = ContextDetailsDialog(self)
        # run modal dialogue
        self._dialog.exec_()
        # seems needs to explicitly close dialog
        self._dialog.close()
        # lastly, need to explicitly delete it, otherwise it stays around in the background.
        self._dialog.deleteLater()
        
        
    
    def _add_command_to_menu(self, name, callback, properties):
        """
        Adds an app command to the menu
        """
        if properties.get("type") == "node":
            # this should go on the custom node menu!
            
            # get icon if specified - default to tank icon if not specified
            icon = properties.get("icon", self._tk2_logo)

            self._node_menu_handle.addCommand(name, callback, icon=icon)

        elif properties.get("type") == "custom_pane":
            # add to the std pane menu in nuke
            self._pane_menu.addCommand(name, callback)
            # also register the panel so that a panel restore command will
            # properly register it on startup or panel profile restore.
            nukescripts.registerPanel(properties.get("panel_id", "undefined"),
                                      callback)

        else:
            # std shotgun menu
            self._menu_handle.addCommand(name, callback) 
            
    def _create_menu(self):
        """
        Render the entire Tank menu.
        """
        # create main menu
        nuke_menu = nuke.menu("Nuke")
        self._menu_handle = nuke_menu.addMenu("Tank") 

        # the right click menu that is displayed when clicking on a pane 
        self._pane_menu = nuke.menu("Pane") 
        
        # slight hack here but first ensure that the menu is empty
        self._menu_handle.clearMenu()

        # create tank side menu
        this_folder = os.path.dirname(__file__)
        self._tk2_logo = os.path.abspath(os.path.join(this_folder, "resources", "logo_gray_22.png"))
        self._tk2_logo_small = os.path.abspath(os.path.join(this_folder, "resources", "logo_color_16.png"))
        self._node_menu_handle = nuke.menu("Nodes").addMenu("Tank", icon=self._tk2_logo)
    
        self.__add_context_menu()
        
        for (cmd_name, cmd_details) in self.commands.items():
            self._add_command_to_menu(cmd_name, cmd_details["callback"], cmd_details["properties"])
            
        self.__add_documentation_to_menu()
            
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
        self._current_queue_item["progress"].set_progress(percent)
    
    def execute_queue(self):
        """
        Executes all items in the queue, one by one, in a controlled fashion
        """
        # create progress items for all queue items
        for x in self._queue:
            x["progress"] = TankProgressWrapper(x["name"], self._ui_enabled)

        # execute one after the other syncronously
        while len(self._queue) > 0:
            
            # take one item off
            self._current_queue_item = self._queue.pop(0)
            
            # process it
            try:
                kwargs = self._current_queue_item["args"]
                # force add a progress_callback arg - this is by convention
                kwargs["progress_callback"] = self.report_progress
                # execute
                self._current_queue_item["method"](**kwargs)
            except:
                # error and continue
                # todo: may want to abort here - or clear the queue? not sure.
                self.log_exception("Error while processing callback %s" % self._current_queue_item)
            finally:
                self._current_queue_item["progress"].close()
        

            
            
            
