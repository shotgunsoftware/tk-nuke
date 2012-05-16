"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Scene Breakdown UI and logic which shows the contents of the scene
 
"""
import nukescripts
import tempfile
import nuke
import os
import platform
import sys
import shutil


class TankBreakdownHandler(object):
    """
    Handles the breakdown UI management methods
    """
    
    def __init__(self, app):
        self._app = app
        
        # since dialog is modal, we can keep a single handle to it
        # this is used in order to get the terrible nuke callbacks to work. 
        self.curr_ui = None
        
        self._templates = []
        for ts in self._app.get_setting("templates_to_look_for", []):
            t = self._app.engine.tank.templates.get(ts)
            if t is None:
                self._app.engine.log_warning("Breakdown Configuration Error: Template %s referred "
                                             "to in the configuration does not exist. It "
                                             "will be ignored." % ts)
            else:
                self._templates.append(t)        

    def breakdown(self):
        """
        Launches the publish dialog
        """ 
        # do the import just before so that this app can run nicely in nuke
        # command line mode,
        from .breakdown_ui import BreakdownPanel
        self.curr_ui = BreakdownPanel(self._app, self._templates)
        #bdp.setMaximumSize(110,410)
        self.curr_ui.setMinimumSize(500,300)
        self.curr_ui.showModal()
        self.curr_ui.hide()
        self.curr_ui = None

