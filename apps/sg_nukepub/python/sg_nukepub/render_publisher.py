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

        
class RenderPublisher(object):
    
    def __init__(self, app, wnh, desc, task, node, node_comment, published_script_path, tank_type=None):
        """
        Publishes a render
        """
        self._app = app
        self._wnh = wnh
        self._task = task
        self._node = node
        self._tank_type = tank_type
        self._published_nuke_script_path = published_script_path

        
        # compile a comment based on the description and the node comment
        if node_comment == "":
            self._render_desc = desc
        else:
            self._render_desc = "%s - %s" % (desc, node_comment)
        
        self._render_name_template = self._app.get_template("template_render_name")
        self._version_name_template = self._app.get_template("template_version_name")
        self._pub_template = self._wnh.get_publish_template(self._node)
        self._render_template = self._wnh.get_render_template(self._node)
        
        # grab files on disk right now - later on the version number
        # may have changed and the location will point elsewhere...
        self._files_on_disk = self._wnh.get_files_on_disk(self._node)
        render_path_pattern = self._wnh.compute_path(self._node)
        self._render_path_fields = self._render_template.get_fields(render_path_pattern)

    def get_channel_name(self):
        """
        Returns the channel name for the node associated with this publisher
        """
        return self._wnh.get_channel_from_node(self._node)

    def preflight_check(self):
        """
        Do sanity checks. Returns False on failure
        """
        # make sure we are not overwriting any files!
        for f in self._files_on_disk:        
            fields = self._render_template.get_fields(f)
            target_path = self._pub_template.apply_fields(fields)
            
            if os.path.exists(target_path):
                nuke.message("The file %s already exists on disk! Cannot publish." % target_path)
                return False
            
        return True
    
    def _process_movies(self, published_sequence, publish_name, version_name, fields, thumb_file):
        """
        Process quicktimes
        """
        
        # compile list of targets to send to hook
        # resolve quicktime templates into paths
        targets = {}
        for x in self._app.resolved_movies_config:
            # targets[ dailies_type ] = path_to_mov
            quicktime_path = self._app.resolved_movies_config[x].apply_fields(fields)
            targets[x] = quicktime_path
        
        # make sure folders exist
        for t in targets:
            target_folder = os.path.dirname(targets[t])
            if not os.path.exists(target_folder):
                # create folder
                self._app.engine.create_folder(target_folder)
        
        # run the hook
        if len(targets) == 0:
            hook_return = {}
        else:
            hook_return = self._app.execute_hook_from_setting("hook_generate_movie",
                                                source_path=published_sequence,
                                                targets=targets)
            
        # now create versions and publishes in Shotgun
        for t in targets:
            
            # see if the hook returned something for this target
            if t not in hook_return:
                # conversion failed! Skip register
                self._app.engine.log_warning("Movie Conversion for target %s failed, "
                                             "will not register this item in Shotgun." % t)
                
            else:
                # movie was fine!
                
                # get the extra sg data that the hook returned
                extra_hook_data = hook_return[t]
                
                # first register publish
                ctx = self._app.engine.context
                sg_user = tank.util.login.get_shotgun_user(self._app.engine.shotgun)
    
                # register in shotgun        
                args = {
                    "sg": self._app.engine.shotgun,
                    "context": ctx,
                    "path": targets[t],
                    "comment": self._render_desc,
                    "name": publish_name,
                    "version_number": fields["version"],
                    "task": self._task,
                    "thumbnail_path": thumb_file,
                    "dependency_paths": [published_sequence],
                }
                tk_pub_entity = tank.util.register_publish(**args)
                    
                # then register version
                data = {
                    "code": version_name,
                    "description": self._render_desc,
                    "project": ctx.project,
                    "entity": ctx.entity,
                    "sg_task": self._task,
                    "sg_movie_type": t,
                    "tank_published_file": tk_pub_entity,
                    "created_by": sg_user,
                    "user": sg_user,
                    "sg_path_to_frames": published_sequence,
                    "sg_path_to_movie": targets[t]
                }
                # and update the dictionary with any values returned from the hook
                # (note that this gives the hook the option to override values too)
                data.update(extra_hook_data)
                # and create                
                entity = self._app.engine.shotgun.create("Version", data)
                # and thumbnail pls
                self._app.engine.shotgun.upload_thumbnail("Version", entity["id"], thumb_file)
            
        
    
    def worker(self, progress_callback):
        """
        Copy the script across then create a SG entity
        """
        # get the templates
        
        # copy all files from source to target path
        num_files = len(self._files_on_disk)
        for idx in xrange(num_files):
            
            src_file = self._files_on_disk[idx]
            percent = int(idx/(float)(num_files))
            
            # set progress
            progress_callback(percent)
            
            # calculate target path
            fields = self._render_template.get_fields(src_file)
            target_path = self._pub_template.apply_fields(fields)
            
            # copy the file
            target_folder = os.path.dirname(target_path)
            if not os.path.exists(target_folder):
                # create folder
                self._app.engine.create_folder(target_folder)
            
            # copy file
            self._app.execute_hook_from_setting("hook_publish_file", source_path=src_file, target_path=target_path)
            
        # generate a thumbnail
        thumb_file = self._wnh.generate_thumbnail(self._node)
        if thumb_file is None:
            # failed - use default thumbnail instead
            thumb_created = False
            thumb_file = os.path.join(self._app.disk_location, "resources", "no_thumb.png")
        else:
            thumb_created = True
        
        # now publish in shotgun
        
        publish_path_pattern = self._pub_template.apply_fields(self._render_path_fields)
        publish_name = self._render_name_template.apply_fields(self._render_path_fields, 
                                                               prepend_tank_project=False)
        version_name = self._version_name_template.apply_fields(self._render_path_fields, 
                                                                prepend_tank_project=False)

        # register in shotgun        
        args = {
            "sg": self._app.engine.shotgun,
            "context": self._app.engine.context,
            "path": publish_path_pattern,
            "comment": self._render_desc,
            "name": publish_name,
            "version_number": self._render_path_fields["version"],
            "task": self._task,
            "thumbnail_path": thumb_file,
            "dependency_paths": [ self._published_nuke_script_path ],
            "tank_type": self._tank_type
        }
        
        tank.util.register_publish(**args)
        
        # now generate quicktimes
        self._process_movies(publish_path_pattern, 
                             publish_name, 
                             version_name, 
                             self._render_path_fields, 
                             thumb_file)
        
        if thumb_created:
            try:
                os.remove(thumb_file)
            except:
                self._app.engine.log_warning("Could not remove temporary thumbnail %s!" % thumb_file)

