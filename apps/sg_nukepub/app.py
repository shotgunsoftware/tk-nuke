"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Publishing and snapshotting in Nuke.

"""

import tank
from tank import TankError
import sys
import nuke
import os

class NukePublish(tank.system.Application):
    
    def init_app(self):
        """
        Called as the application is being initialized
        """
        
        import sg_nukepub 

        # validate template_work and template_publish have the same extension
        _, work_ext = os.path.splitext(
            self.engine.tank.templates.get(self.get_setting('template_work')).definition)

        _, pub_ext = os.path.splitext(
            self.engine.tank.templates.get(self.get_setting('template_publish')).definition)
        
        if work_ext != pub_ext:
            # disable app
            self.engine.log_error("'template_work' and 'template_publish' have different file extensions.")
            return
        # end if
        
        # create handlers for our various commands
        self.write_node_handler = sg_nukepub.TankWriteNodeHandler(self)
        self.snapshot_handler = sg_nukepub.TankSnapshotHandler(self)
        self.publish_handler = sg_nukepub.TankPublishHandler(self, 
                                                             self.snapshot_handler,
                                                             self.write_node_handler)

        # add stuff to main menu
        self.engine.register_command("Snapshot As...", self.snapshot_handler.snapshot_as)
        self.engine.register_command("Snapshot", self.snapshot_handler.snapshot)
        self.engine.register_command("Publish...", self.publish_handler.publish)
        self.engine.register_command("Version up Work file...", self.snapshot_handler.manual_version_up)

        self.__add_write_nodes()
        self.__add_recent_files_menu()
        
        self.resolved_movies_config = {}
        self.__load_movie_settings()
                                      
    def destroy_app(self):
        self.engine.log_debug("Destroying sg_breakdown")
                       
    def __load_movie_settings(self):
        """
        Loads and validates the quicktime config
        """
        
        for x in self.get_setting("movies", []):
            if not isinstance(x, dict):
                raise TankError("Invalid quicktime configuration %s" % x)
            movie_type = x.get("type")
            if movie_type is None:
                raise TankError("Invalid quicktime configuration %s: Missing type field." % x)
            ts = x.get("template")
            if ts is None:
                raise TankError("Invalid quicktime configuration %s: Missing template field." % x)
            template = self.engine.tank.templates.get(ts)
            if template is None:
                raise TankError("Invalid quicktime configuration %s: Template cannot be resolved!" % x)
            # add to movies dict
            self.resolved_movies_config[movie_type] = template
            
                       
    def __generate_create_node_callback_fn(self, name, render_templ, publish_templ, file_type, file_settings):
        """
        Helper
        Creates a callback function for the tank write node
        """
        cb_fn = (lambda n=name, rt=render_templ, pt=publish_templ, ft=file_type, ts=file_settings: 
                 self.write_node_handler.create_new_node(n, rt, pt, ft, ts))
        return cb_fn          
                                      
    def __add_write_nodes(self):
        """
        Creates write node menu entries for all write node configurations
        """
        write_node_icon = os.path.join(self.disk_location, "resources", "tk2_write.png")
        
        for x in self.get_setting("write_nodes", []):
            # each write node has a couple of entries
            name = x.get("name", "unknown")
            file_type = x.get("file_type")
            file_settings = x.get("settings", {})
            if not isinstance(file_settings, dict):
                raise TankError("Configuration Error: Write node contains invalid settings. "
                                     "Settings must be a dictionary. Current config: %s" % x)
            
            rts = x.get("render_template")
            if rts is None:
                raise TankError("Configuration Error: Write node has no render_template: %s" % x)
            
            pts = x.get("publish_template")
            if pts is None:
                raise TankError("Configuration Error: Write node has no publish_template: %s" % x)

            render_template = self.engine.tank.templates.get(rts)
            if render_template is None:
                raise TankError("Configuration Error: Could not find render template: %s" % x)

            publish_template = self.engine.tank.templates.get(pts)
            if publish_template is None:
                raise TankError("Configuration Error: Could not find publish template: %s" % x)

            # make sure that all required fields exist in the templates
            for x in ["version", "name", "channel"]:
                if x not in render_template.keys.keys():
                    raise TankError("Configuration Error: The required field '%s' is missing" 
                                         "from the template %s" % (x, render_template))
                if x not in publish_template.keys.keys():
                    raise TankError("Configuration Error: The required field '%s' is missing" 
                                         "from the template %s" % (x, publish_template))

            # add stuff to toolbar menu        
            cb_fn = self.__generate_create_node_callback_fn(name, 
                                                            render_template, 
                                                            publish_template,
                                                            file_type, 
                                                            file_settings)
            self.engine.register_command("Tank Write: %s" % name, 
                                          cb_fn, 
                                          {"type": "node", "icon": write_node_icon})
        
                                         
    def __add_recent_files_menu(self):
        """
        Creates a recent file menu and adds it to the engine context menu
        """
        
        # add recent items to the context menu
        # data structure for organising stuff
        work_items = {}
        # now get all work items
        tw = self.get_template("template_work")
        ctx_fields = self.engine.context.as_template_fields(tw)
        for wi in self.engine.tank.find_files(tw, ctx_fields):
            # get the fields
            fields = tw.get_fields(wi)
            name = fields["name"]
            version = fields["version"]
            if not name in work_items:
                work_items[name] = {}
            work_items[name][version] = wi
            
        # we now have a dict like this    
        # {"name1": {1:"/path", 2:"/path"}, "name2": {...}}
        # now create menu items
        for name in sorted(work_items.keys()):
            max_ver = max(work_items[name].keys())
            path = work_items[name][max_ver]
            self.engine.register_command("Open Work Item/%s.nk (v. %d)" % (name, max_ver), 
                                         self.__generate_recent_file_callback_fn(path),
                                         {"type": "context_menu"})
                        
    def __generate_recent_file_callback_fn(self, path):
        """
        Helper.
        Returns a function which will open the nuke file specified in path
        """
        cb_fn = lambda file_name=path: nuke.scriptOpen(file_name)
        return cb_fn
        

