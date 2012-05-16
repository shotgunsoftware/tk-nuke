"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Example code for a quicktime creator app that runs in Nuke
"""

import os
import sys
import nuke
import tank

class QuicktimeGenerator(tank.system.Application):



    def init_app(self):
        
        self._logo = os.path.join(self.disk_location, "resources", "logo.png")
        self._font = os.path.join(self.disk_location, "resources", "liberationsans_regular.ttf")

        self._nodes = []
        self._outputs = []
        
    def reset(self):
        """
        Delete any nodes created by this app
        """
        for x in self._outputs:
            nuke.delete(x)
        self._outputs = []
        for x in self._nodes:
            nuke.delete(x)
        self._nodes = []

    def get_first_frame(self):
        """
        returns the first frame for this session
        """
        return int(nuke.root()["first_frame"].value())
        
    def get_last_frame(self):
        """
        returns the last frame for this session
        """
        return int(nuke.root()["last_frame"].value())
    
    def set_up_input(self, path):
        """
        Sets up the input for the render
        """
        
        # create read node
        self._src = nuke.nodes.Read(name="source", file=path)
        self._src["on_error"].setValue("black")
        self._src["first"].setValue(self.get_first_frame())
        self._src["last"].setValue(self.get_last_frame())
        self._nodes.append(self._src)
        
        # now create the slate/burnin node
        self._burnin = nuke.nodes.sg_make_quicktime()
        self._burnin.setInput(0, self._src)
        self._nodes.append(self._burnin)
    
        # set the fonts for all text fields
        self._burnin.node("top_left_text")["font"].setValue(self._font)
        self._burnin.node("top_right_text")["font"].setValue(self._font)
        self._burnin.node("bottom_left_text")["font"].setValue(self._font)
        self._burnin.node("framecounter")["font"].setValue(self._font)
        self._burnin.node("slate_info")["font"].setValue(self._font)
    
        # add the logo
        self._burnin.node("logo")["file"].setValue(self._logo)
    
        # pull some metadata out of the context and the file
        template = self.engine.tank.resolve(path)
        fields = template.get_fields(path)
        context = tank.system.Context.from_path(path)

        # format the burnins  
        ver = fields.get("version", 0)
        if context.task:
            version = "%s, version %03d" % (context.task["name"], ver)
        elif context.step:
            version = "%s, version %03d" % (context.step["name"], ver)
        else:
            version = "Version %03d" % ver
        
        self._burnin.node("top_left_text")["message"].setValue(context.project["name"])
        self._burnin.node("top_right_text")["message"].setValue(context.entity["name"])
        self._burnin.node("bottom_left_text")["message"].setValue(version)
        
        # and the slate
        slate_str =  "Project: %s\n" % context.project["name"]
        slate_str += "%s: %s\n" % (context.entity["type"], context.entity["name"])
        slate_str += "Version: %03d\n" % fields.get("version", 0)
        
        if context.task:
            slate_str += "Task: %s\n" % context.task["name"]
        elif context.step:
            slate_str += "Step: %s\n" % context.step["name"]
        
        slate_str += "Frames: %s - %s\n" % (self.get_first_frame(), self.get_last_frame())
        
        self._burnin.node("slate_info")["message"].setValue(slate_str)
        
    
    def add_quicktime_output(self, profile, path):
        """
        adds a qucktime output
        """

        prof =  self.get_setting("profiles", {}).get(profile)
        if prof is None:
            raise tank.TankError("Could not find a configuration profile named %s!" % profile)
 
        width = prof.get("width")
        height = prof.get("height")
        
        if width is not None and height is not None:
            # create a scale node
            scale = nuke.nodes.Reformat()
            self._nodes.append(scale)
            scale["type"].setValue("to box")
            scale["box_width"].setValue(width)
            scale["box_height"].setValue(height)
            scale["resize"].setValue("fit")
            scale["box_fixed"].setValue(True)
            scale["center"].setValue(True)
            scale["black_outside"].setValue(True)
            scale.setInput(0, self._burnin)
                
            output = nuke.nodes.Write()
            output.setInput(0, scale)
        else:
            output = nuke.nodes.Write()
            output.setInput(0, self._burnin)
            
        self._outputs.append(output)
        output["file"].setValue(path)
        
        ################################################################
        # example output settings
        # these are either hard coded by a studio in a quicktime generation 
        # app itself (like here)
        # or part of the configuration - however there is often the need to
        # have special rules to for example handle multi platform cases.
        
        # on the mac and windows, we use the quicktime codec
        # on linux, use ffmpeg
        if sys.platform == "darwin" or sys.platform == "win32":
            output["file_type"].setValue("mov")
            output["codec"].setValue("jpeg")

        elif sys.platform == "linux2":
            output["file_type"].setValue("ffmpeg")
            output["codec"].setValue("MOV format (mov)")

        

        
    def render(self):
        """
        Executes the render, always renders the first view.
        """
        if len(self._outputs) == 0:
            return
        
        first_view = nuke.views()[0]        
        nuke.executeMultiple( self._outputs, 
                              ([ self.get_first_frame()-1, self.get_last_frame(), 1 ],),
                              [first_view]
                              )
        


