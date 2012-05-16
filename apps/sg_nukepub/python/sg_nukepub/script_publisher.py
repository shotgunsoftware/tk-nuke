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


class ScriptPublisher(object):
    
    def __init__(self, app, snh, scene_file, desc, task, tank_type=None):
        """
        Publishes a script
        """
        self._app = app
        self._snapshot_handler = snh
        self._scene_file = scene_file
        self._desc = desc
        self._task = task
        self._tank_type = tank_type
        
        self._work_template = self._app.get_template("template_work")
        self._publish_template = self._app.get_template("template_publish")
        self._publish_name_template = self._app.get_template("template_publish_name")
        
        
    def preflight_check(self):
        """ 
        Do a bunch of checks prior to processing
        """
        # figure out the publish location
        fields = self._work_template.get_fields(self._scene_file)
        pub_path = self._publish_template.apply_fields(fields)
        
        # now some validation checks
        if os.path.exists(pub_path):
            # pub path taken
            nuke.message("The publish file \n%s \nalready exists on disk!\n"
                         "Please snapshot-as before proceeding." % pub_path)
            return False
                
        # check next snapshot version
        if not self._snapshot_handler.validate_publish_snapshot(self._scene_file):
            return False
        
        # all good
        return True

    def pub_path(self):
        fields = self._work_template.get_fields(self._scene_file)
        pub_path = self._publish_template.apply_fields(fields)
        return pub_path
    
    def worker(self, progress_callback):
        """
        Copy the script across then create a SG entity
        """
        # figure out the publish location
        fields = self._work_template.get_fields(self._scene_file)
        pub_path = self._publish_template.apply_fields(fields)
        pub_name = self._publish_name_template.apply_fields(fields, prepend_tank_project=False)
        
        # first version up the snapshot
        self._snapshot_handler.publish_snapshot(self._scene_file)
        
        # create publish file
        pub_folder = os.path.dirname(pub_path)
        if not os.path.exists(pub_folder):
            # create folder
            self._app.engine.create_folder(pub_folder)
        
        # copy the file
        self._app.execute_hook_from_setting("hook_publish_file", source_path=self._scene_file, target_path=pub_path)
         
        # no thumb image
        no_thumb_path = os.path.join(self._app.disk_location, "resources", "no_thumb.png")
        
        # figure out all the inputs to the scene and pass them as dependency candidates
        dependency_paths = []
        for read_node in nuke.allNodes('Read'):
            # make sure we normalize file paths
            file_name = read_node.knob("file").evaluate().replace('/', os.path.sep)
            # validate against all our templates
            for template_name in self._app.get_setting("input_templates_to_look_for"):
                template = self._app.engine.tank.templates.get(template_name)
                if template.validate(file_name):
                    fields = template.get_fields(file_name)
                    # translate into a form that represents the general
                    # tank write node path.
                    fields["SEQ"] = "%04d"
                    fields["eye"] = "%V"
                    dependency_paths.append(template.apply_fields(fields))
        
        
        # register in shotgun        
        args = {
            "sg": self._app.engine.shotgun,
            "context": self._app.engine.context,
            "path": pub_path,
            "comment": self._desc,
            "name": pub_name,
            "version_number": fields["version"],
            "task": self._task,
            "thumbnail_path": no_thumb_path,
            "dependency_paths": dependency_paths,
            "tank_type": self._tank_type,
        }
        
        tank.util.register_publish(**args)
        


