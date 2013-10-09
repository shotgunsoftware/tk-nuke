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
Menu handling for Nuke

"""

import tank
import sys
import nuke
import os
import unicodedata
import nukescripts.openurl

import nukescripts




class MenuGenerator(object):
    """
    Menu generation functionality for Nuke
    """

    def __init__(self, engine, menu_name):
        self._engine = engine
        self._menu_name = menu_name
        self._dialogs = []
        engine_root_dir = self._engine.disk_location
        self.tank_logo = os.path.abspath(os.path.join(engine_root_dir, "resources", "logo_gray_22.png"))

    ##########################################################################################
    # public methods

    def create_menu(self):
        """
        Render the entire Shotgun menu.
        """
        # create main menu
        nuke_menu = nuke.menu("Nuke")
        menu_handle = nuke_menu.addMenu(self._menu_name) 
        
        # the right click menu that is displayed when clicking on a pane 
        self._pane_menu = nuke.menu("Pane") 
        # create tank side menu
        node_menu_handle = nuke.menu("Nodes").addMenu(self._menu_name, icon=self.tank_logo)

        # slight hack here but first ensure that the menu is empty
        menu_handle.clearMenu()
    
    
        
        # now add the context item on top of the main menu
        self._context_menu = self._add_context_menu(menu_handle)
        menu_handle.addSeparator()

        # now enumerate all items and create menu objects for them
        menu_items = []
        for (cmd_name, cmd_details) in self._engine.commands.items():
             menu_items.append( AppCommand(cmd_name, cmd_details) )

        # sort list of commands in name order
        menu_items.sort(key=lambda x: x.name)

        # now add favourites
        for fav in self._engine.get_setting("menu_favourites"):
            app_instance_name = fav["app_instance"]
            menu_name = fav["name"]
            
            # scan through all menu items
            for cmd in menu_items:                 
                 if cmd.get_app_instance_name() == app_instance_name and cmd.name == menu_name:
                     # found our match!
                     cmd.add_command_to_menu(menu_handle)
                     # mark as a favourite item
                     cmd.favourite = True            

        menu_handle.addSeparator()
        
        
        # now go through all of the menu items.
        # separate them out into various sections
        commands_by_app = {}
        
        for cmd in menu_items:
                        
            if cmd.get_type() == "node":
                # add to the node menu
                # get icon if specified - default to tank icon if not specified
                icon = cmd.properties.get("icon", self.tank_logo)
                node_menu_handle.addCommand(cmd.name, cmd.callback, icon=icon)
                
            elif cmd.get_type() == "custom_pane":
                # custom pane
                # add to the std pane menu in nuke
                icon = cmd.properties.get("icon")
                self._pane_menu.addCommand(cmd.name, cmd.callback, icon=icon)
                # also register the panel so that a panel restore command will
                # properly register it on startup or panel profile restore.
                nukescripts.registerPanel(cmd.properties.get("panel_id", "undefined"), cmd.callback)
                
            elif cmd.get_type() == "context_menu":
                # context menu!
                cmd.add_command_to_menu(self._context_menu)
                
            else:
                # normal menu
                app_name = cmd.get_app_name()
                if app_name is None:
                    # un-parented app
                    app_name = "Other Items" 
                if not app_name in commands_by_app:
                    commands_by_app[app_name] = []
                commands_by_app[app_name].append(cmd)
        
        # now add all apps to main menu
        self._add_app_menu(commands_by_app, menu_handle)
            
            
    def destroy_menu(self):

        # important!
        # the menu code in nuke seems quite unstable, so make sure to test 
        # any changes done in relation to menu deletion carefully.
        # the removeItem() method seems to work on some version of Nuke, but not all.
        # for example the following code works in nuke 7, not nuke 6:
        # nuke.menu("Nuke").removeItem("Shotgun")
        
        # the strategy below is to be as safe as possible, acquire a handle to 
        # the menu by iteration (if you store the handle object, they may expire
        # and when you try to access them they underlying object is gone and things 
        # will crash). clearMenu() seems to work on both v6 and v7.

        # find our Shotgun menu and clear it
        for mh in nuke.menu("Nuke").items():
            if mh.name() == self._menu_name:
                mh.clearMenu()
         
        # find the toolbar menu and clear it
        for mh in nuke.menu("Pane").items():
            if mh.name() == self._menu_name:
                mh.clearMenu()        
        
    ##########################################################################################
    # context menu and UI

    def _add_context_menu(self, menu_handle):
        """
        Adds a context menu which displays the current context
        """        
        
        ctx = self._engine.context
        ctx_name = str(ctx)
        
        # create the menu object        
        ctx_menu = menu_handle.addMenu(ctx_name)
        ctx_menu.addCommand("Jump to Shotgun", self._jump_to_sg)
        ctx_menu.addCommand("Jump to File System", self._jump_to_fs)
        ctx_menu.addSeparator()
        
        return ctx_menu
                        
    
    def _jump_to_sg(self):
        """
        Jump to shotgun, launch web browser
        """
        from tank.platform.qt import QtCore, QtGui        
        url = self._engine.context.shotgun_url
        nukescripts.openurl.start(url)        
        
    def _jump_to_fs(self):
        
        """
        Jump from context to FS
        """
        # launch one window for each location on disk
        paths = self._engine.context.filesystem_locations
        for disk_location in paths:
                
            # get the setting        
            system = sys.platform
            
            # run the app
            if system == "linux2":
                cmd = 'xdg-open "%s"' % disk_location
            elif system == "darwin":
                cmd = 'open "%s"' % disk_location
            elif system == "win32":
                cmd = 'cmd.exe /C start "Folder" "%s"' % disk_location
            else:
                raise Exception("Platform '%s' is not supported." % system)
            
            exit_code = os.system(cmd)
            if exit_code != 0:
                self._engine.log_error("Failed to launch '%s'!" % cmd)
        
            
    ##########################################################################################
    # app menus
        
        
    def _add_app_menu(self, commands_by_app, menu_handle):
        """
        Add all apps to the main menu, process them one by one.
        """
        for app_name in sorted(commands_by_app.keys()):
            
            
            if len(commands_by_app[app_name]) > 1:
                # more than one menu entry fort his app
                # make a sub menu and put all items in the sub menu
                app_menu = menu_handle.addMenu(app_name)
                
                # get the list of menu cmds for this app
                cmds = commands_by_app[app_name]
                # make sure it is in alphabetical order
                cmds.sort(key=lambda x: x.name) 
                
                for cmd in cmds:
                    cmd.add_command_to_menu(app_menu)
                            
            else:
                # this app only has a single entry. 
                # display that on the menu
                # todo: Should this be labelled with the name of the app 
                # or the name of the menu item? Not sure.
                cmd_obj = commands_by_app[app_name][0]
                if not cmd_obj.favourite:
                    # skip favourites since they are alreay on the menu
                    cmd_obj.add_command_to_menu(menu_handle)
                                
        
        
    
            
class AppCommand(object):
    """
    Wraps around a single command that you get from engine.commands
    """
    
    def __init__(self, name, command_dict):        
        self.name = name
        self.properties = command_dict["properties"]
        self.callback = command_dict["callback"]
        self.favourite = False
        
        
    def get_app_name(self):
        """
        Returns the name of the app that this command belongs to
        """
        if "app" in self.properties:
            return self.properties["app"].display_name
        return None
        
    def get_app_instance_name(self):
        """
        Returns the name of the app instance, as defined in the environment.
        Returns None if not found.
        """
        if "app" not in self.properties:
            return None
        
        app_instance = self.properties["app"]
        engine = app_instance.engine

        for (app_instance_name, app_instance_obj) in engine.apps.items():
            if app_instance_obj == app_instance:
                # found our app!
                return app_instance_name
            
        return None
        
    def get_documentation_url_str(self):
        """
        Returns the documentation as a str
        """
        if "app" in self.properties:
            app = self.properties["app"]
            doc_url = app.documentation_url
            # deal with nuke's inability to handle unicode. #fail
            if doc_url.__class__ == unicode:
                doc_url = unicodedata.normalize('NFKD', doc_url).encode('ascii', 'ignore')
            return doc_url

        return None
        
    def get_type(self):
        """
        returns the command type. Returns node, custom_pane or default
        """
        return self.properties.get("type", "default")
        
    def add_command_to_menu(self, menu):
        """
        Adds an app command to the menu
        """
        # std shotgun menu
        icon = self.properties.get("icon")
        hotkey = self.properties.get("hotkey")
        if hotkey:
            menu.addCommand(self.name, self.callback, hotkey, icon=icon) 
        else:
            menu.addCommand(self.name, self.callback, icon=icon) 













    
