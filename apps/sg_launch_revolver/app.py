"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

An app that launches revolver from nuke

"""

import sys
import os
import platform

from tank.system import Application

class NukeLaunchRevolver(Application):
    
    def init_app(self):
        self.context = self.engine.context
        self.engine.register_command("Jump into Revolver", self._start_revolver)
        
    def _get_rv_binary(self):
        """
        Returns the RV binary to run
        """
        # get the setting        
        system = platform.system()
        try:
            app_setting = {"Linux": "rv_path_linux", "Darwin": "rv_path_mac", "Windows": "rv_path_windows"}[system]
            app_path = self.get_setting(app_setting)
            if not app_path: raise KeyError()
        except KeyError:
            raise Exception("Platform '%s' is not supported." % system) 
        
        if system == "Darwin":
            # append Contents/MacOS/RV64 to the app bundle path
            app_path = os.path.join(app_path, "Contents/MacOS/RV64") 
        
        return app_path
        
    def _start_revolver(self):
        import sg_launch_revolver
        
        # figure out the context for revolver
        # first try to get a version
        # if that fails try to get the current entity
        context = None
        task = self.engine.context.task
        if task:
            # look for versions matching this task!
            self.engine.log_debug("Looking for versions connected to %s..." % task)
            filters = [["sg_task", "is", task]]
            order   = [{"field_name": "created_at", "direction": "desc"}]
            fields  = ["id"]
            version = self.engine.shotgun.find_one("Version", 
                                                       filters=filters, 
                                                       fields=fields, 
                                                       order=order)
            if version:
                # got a version
                context = self.engine.context.task

        if context is None:
            # fall back on entity
            context = self.engine.context.entity
        
        self.engine.log_debug("Launching revolver for context %s" % context)
        
        try:
            sg_launch_revolver.revolver.launch_timeline( base_url=self.engine.shotgun.base_url, 
                                                         context=context,
                                                         path_to_rv=self._get_rv_binary() )
        except Exception, e:
            self.engine.log_error("Could not launch revolver - check your configuration! "
                                  "Error reported: %s" % e)
    
