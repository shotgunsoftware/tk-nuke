"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

A breakdown window in Nuke which shows all inputs and what is out of date.

"""

import tank
import sys
import nuke
import os

class NukeBreakdown(tank.system.Application):
    
    def init_app(self):
        """
        Called as the application is being initialized
        """
        import sg_breakdown
                
        # create handlers for our various commands
        self.bdh = sg_breakdown.TankBreakdownHandler(self)

        # add stuff to main menu
        self.engine.register_command("Scene Breakdown...", self.bdh.breakdown)

    def destroy_app(self):
        self.engine.log_debug("Destroying sg_breakdown")

