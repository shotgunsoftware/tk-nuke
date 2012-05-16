"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

An app that syncs the frame range between a nuke script and a shot in Shotgun.

"""

import sys
import os
import nuke

from tank.system import Application

class NukeSetFrameRange(Application):
    
    def init_app(self):
        self.context = self.engine.context
        self.engine.register_command("Sync Frame Range with Shotgun", self._set_frame_range)

    def destroy_app(self):
        self.engine.log_debug("Destroying sg_set_frame_range")
        
    def _set_frame_range(self):

        current_in = nuke.root()["first_frame"].value()
        current_out = nuke.root()["last_frame"].value()
        entity = self.context.entity
        
        if entity["type"] != "Shot":    
            nuke.message("Currently only works for Shots!")
            
        else:
            filters = [["id", "is", entity["id"]]]
            fields = ["sg_cut_in", "sg_cut_out"]
            sg_entity = self.engine.shotgun.find_one("Shot", filters=filters, fields=fields)
            
            if sg_entity:
                new_in = sg_entity["sg_cut_in"]
                new_out = sg_entity["sg_cut_out"]
                
                if new_in is None or new_out is None:
                    message =  "Shotgun has not yet been populated with \n"
                    message += "in and out frame data for this Shot."
                
                elif int(new_in) != int(current_in) or int(new_out) != int(current_out):
                    # change!
                    message =  "Your scene has been updated with the \n"
                    message += "latest frame ranges from shotgun.\n\n"
                    message += "Previous start frame: %d\n" % current_in
                    message += "New start frame: %d\n\n" % new_in
                    message += "Previous end frame: %d\n" % current_out
                    message += "New end frame: %d\n\n" % new_out
                    
                    # unlock
                    locked = nuke.root()["lock_range"].value()
                    if locked:
                        nuke.root()["lock_range"].setValue(False)
                    # set values  
                    nuke.root()["first_frame"].setValue(new_in)
                    nuke.root()["last_frame"].setValue(new_out)
                    # and lock again
                    if locked:
                        nuke.root()["lock_range"].setValue(True)
                    
                else:
                    # no change
                    message = "Already up to date!\n\n"
                    message += "Your scene is already in sync with the\n"
                    message += "start and end frames in shotgun.\n\n"
                    message += "No changes were made."
                    
                nuke.message(message)



 