"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

"""
import nuke
import tank
import time
import nukescripts
import tempfile
import os
import sys
import shutil

from tank import TankError
from .render_publisher import RenderPublisher
from .script_publisher import ScriptPublisher



class TankPublishHandler(object):
    """
    Handles the publishing logic
    """
    
    def __init__(self, app, snapshot_handler, write_node_handler):
        self._app = app
        self._work_template = self._app.get_template("template_work")
        self._snapshot_handler = snapshot_handler
        self._write_node_handler = write_node_handler
        

    def publish(self):
        """
        Launches the publish dialog
        """ 
        
        # if file is not ever saved, ask user to snapshot 
        if nuke.root().name() == "Root":
            nuke.message("Please snapshot first!")
            return
                    
        # convert slashes to native os style..
        scene_file = nuke.root().name().replace("/", os.path.sep)
            
        # make sure that the current file is actually a tank snapshot file
        if not self._work_template.validate(scene_file):
            
            # not a work file!
            nuke.message("The current file is not a Tank work file. "
                         "Please do a Snapshot As before publishing!")
            self._snapshot_handler.snapshot_as()
            return
            
            
        # ask user for some stuff via publish UI
        
        # defer import to make sure that the module works in 
        # command line mode
        from .publish_ui import PublishPanel
        pub_ui = PublishPanel(self._app, self._write_node_handler)
        
        pub_ui.showModal()
        
        if pub_ui.cancelled():
            return
                
        ### ok all good prepare for submission
        desc = pub_ui.get_description()
        task = pub_ui.get_task()
        tank_type = pub_ui.get_tank_type()
        
        # make sure the file is saved
        nuke.scriptSave()
        
        # create submitter objects
        sp = ScriptPublisher(self._app, self._snapshot_handler, scene_file, desc, task, tank_type=tank_type)
        rps = list()
        for x in pub_ui.get_render_settings():
            if x["enabled"]:
                rps.append( RenderPublisher(self._app, 
                                            self._write_node_handler, 
                                            desc, 
                                            task, 
                                            x["node"], 
                                            x["comment"], 
                                            sp.pub_path(),
                                            tank_type=x['tank_type']))                
        
        # do checks before we start
        status = True
        status &= sp.preflight_check()
        for rp in rps:
            status &= rp.preflight_check()
        
        if not status:
            return False
        
        # now queue up all items
        self._app.engine.add_to_queue("Publishing Work File", sp.worker, {})
        for rp in rps:
            self._app.engine.add_to_queue("Publishing Render Node %s" % rp.get_channel_name(), 
                                          rp.worker, 
                                          {})
        
        
        # and finally execute
        self._app.engine.execute_queue()
        
        nuke.message("Your work has been shared, your scene has been versioned up and your mates have been notified.")
        
        
        
