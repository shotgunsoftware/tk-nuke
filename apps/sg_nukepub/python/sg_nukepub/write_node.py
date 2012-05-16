"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

"""

import os
import sys
import subprocess
import nuke
import tempfile
import nukescripts
import textwrap
import tank
import platform

class TankWriteNodeHandler(object):
    """
    Handles requests and processing from a tank write node.
    """

    def __init__(self, app):
        self._app = app
        self._work_template = self._app.get_template("template_work")        
    
    def get_render_template(self, node):
        """
        helper function. Returns the associated render template obj for a node
        """
        templ_name = node.knob("render_template").value()
        
        return self._app.engine.tank.templates.get(templ_name)        
        
    def get_publish_template(self, node):
        """
        helper function. Returns the associated pub template obj for a node
        """
        templ_name = node.knob("publish_template").value()
        return self._app.engine.tank.templates.get(templ_name)        

    def _update_path_preview(self, node, path):
        """
        Updates the path preview fields on the tank write node.
        """        
        
        # first set up the node label
        ch = node.knob("tank_channel").value()
        pn = node.knob("profile_name").value()
        label = "Tank Write %s, Channel %s" % (pn, ch)
        node.knob("label").setValue(label)
        
        # normalize the path for os platform
        norm_path = path.replace("/", os.sep)
        
        # get the file name
        filename = os.path.basename(norm_path)
        render_dir = os.path.dirname(norm_path)
        
        # now get the context path
        context_path = None
        for x in self._app.engine.context.entity_locations:
            if render_dir.startswith(x):
                context_path = x
        
        if context_path:
            # found a context path!
            # chop off this bit from the normalized path
            local_path = render_dir[len(context_path):]
            # drop start slash
            if local_path.startswith(os.sep):
                local_path = local_path[len(os.sep):]
            # e.g. for path   /mnt/proj/shotXYZ/renders/v003/hello.%04d.exr 
            # context_path:   /mnt/proj/shotXYZ
            # local_path:     renders/v003
        else:
            # skip the local path
            context_path = render_dir
            local_path = ""
            # e.g. for path   /mnt/proj/shotXYZ/renders/v003/hello.%04d.exr 
            # context_path:   /mnt/proj/shotXYZ/renders/v003
            # local_path:     
            
        pn = node.knob("path_context")
        pn.setValue(context_path)
        pn = node.knob("path_local")
        pn.setValue(local_path)
        pn = node.knob("path_filename")
        pn.setValue(filename)
        

    def __populate_channel_name(self, template, node):
        """
        Create a suitable channel name for a node
        """
        # look at all other nodes to determine the channel
        # name so that we don't produce a duplicate
        channel_names = []
        for n in nuke.allNodes("WriteTank"):
            ch_knob = n.knob("tank_channel")
            channel_names.append(ch_knob.evaluate())
        
        # try to get default channel name from template
        nk = template.keys["channel"]
        if nk.default is None:
            # no default name - use hard coded built in
            channel_name_base = "main"
        else:
            channel_name_base = nk.default
        
        # look at other nodes to ensure uniqueness
        channel_name = channel_name_base
        counter = 0
        while channel_name in channel_names:
            counter += 1
            channel_name = "%s%d" % (channel_name_base, counter)
            
        channel_knob = node.knob("tank_channel")
        channel_knob.setValue(channel_name)    
        
    def __populate_format_settings(self, node, file_type, file_settings):
        """
        Controls the file format of the write node
        """
        # get the embedded write node
        write_node = node.node("Write1") 
        # set the file_type
        write_node.knob("file_type").setValue(file_type)
        # now have to read it back and check that the value is what we 
        # expect. Cheers Nuke.
        if write_node.knob("file_type").value() != file_type:
            self._app.engine.log_error("Tank write node configuration refers to an invalid file "
                                       "format '%s'! Will revert to auto-detect mode." % file_type)
            write_node.knob("file_type").setValue("  ")
            return
        
        # now apply file format settings
        for x in file_settings:
            knob = write_node.knob(x)
            val_to_set = file_settings[x]
            if knob is None:
                self._app.engine.log_error("Invalid setting for file format %s - %s: %s. This "
                                           "will be ignored." % (file_type, x, val_to_set)) 
            else:
                knob.setValue(val_to_set)
                val = knob.value() 
                if val != val_to_set:
                    self._app.engine.log_error("Could not set %s file format setting %s: '%s'. Instead "
                                               "the value was set to '%s'" % (file_type, x, val_to_set, val))
                

    def create_new_node(self, name, render_template, pub_template, file_type, file_settings):
        """
        Creates a new write node
        
        :returns: a node object.
        """
        if nuke.root().name() == "Root":
            # must snapshot first!
            nuke.message("Please snapshot the file first!")
            return
        
        # make sure that the file is a proper tank work path
        curr_filename = nuke.root().name().replace("/", os.path.sep)            
        if not self._work_template.validate(curr_filename):
            nuke.message("This file is not a Tank work file. Please do a snapshot as in order "
                         "to save it as a Tank work file.")
            return
            
        # new node please!
        node = nuke.createNode("WriteTank")
        self._app.engine.log_debug("Created Tank Write Node %s" % node.name())
        
        # auto-populate channel name based on template
        self.__populate_channel_name(render_template, node)
        
        # write the template name to the node so that we know it later
        node.knob("render_template").setValue(render_template.name)
        node.knob("publish_template").setValue(pub_template.name)
        node.knob("profile_name").setValue(name)

        # set the format
        self.__populate_format_settings(node, file_type, file_settings)
            
        # calculate the preview path
        self._update_path_preview(node, self.compute_path(node))
                
        return node
    
    
    def compute_path(self, node):
        """
        Computes the path for a node.
        
        :returns: a path based on the node settings 
        """
        # note! Nuke has got pretty good error handling so don't try to catch any exceptions.
        
        curr_filename = nuke.root().name().replace("/", os.path.sep)            
        if not self._work_template.validate(curr_filename):
            raise Exception("Not a Tank Work File!")
        
        # get the template
        template = self.get_render_template(node)

        # now validate the channel name
        chan_name = node.knob("tank_channel").evaluate()
        if not template.keys["channel"].validate(chan_name):
            raise tank.TankError("Channel name '%s' contains illegal characters!" % chan_name) 
        
        # get fields from curr open nuke script
        work_file_fields = self._work_template.get_fields(curr_filename)
        
        # create fields dict with all the metadata
        
        # TODO: tank write node currently only handles four zero padding (with the %04d SEQ field)
        # make this more generic.
        
        fields = {}
        fields["width"] = nuke.root().width()
        fields["height"] = nuke.root().height()
        fields["name"] = work_file_fields["name"]
        fields["version"] = work_file_fields["version"]
        fields["SEQ"] = "%04d"
        fields["channel"] = chan_name
        # use %V - full view printout as default for the eye field
        fields["eye"] = "%V"
        fields.update(self._app.engine.context.as_template_fields(template))
        
        # get a path from tank
        render_path = template.apply_fields(fields)
        
        return render_path
                        
    def on_compute_path_gizmo_callback(self, node):
        """
        callback executed when nuke requests the location of the std output to be computed.
        returns a path on disk. This will return the path ion a form that Nuke likes 
        (eg. with slashes). It also updates the preview fields on the node.
        """
        # compute path
        render_path = self.compute_path(node)
        # and back to slash notation for paths again
        render_path = render_path.replace(os.path.sep, "/")
        # and update preview
        self._update_path_preview(node, render_path)

        return render_path
        
    def generate_thumbnail(self, node):
        """
        generates a thumbnail in a temp location and returns the path to it.
        It is the responsibility of the caller to delete this thumbnail afterwards.
        The thumbnail will be in png format.
        
        Returns None if no thumbnail could be generated
        """
        # get thumbnail node
        
        th_node = node.node("create_thumbnail")
        th_node.knob('disable').setValue(False)
        if th_node is None:
            # write gizmo that does not have the create thumbnail node
            return None
        
        png_path = tempfile.NamedTemporaryFile(suffix=".png", prefix="tanktmp", delete=False).name
        
        # set render output - make sure to use a path with slashes on all OSes
        th_node.knob("file").setValue(png_path.replace(os.path.sep, "/"))
        th_node.knob("proxy").setValue(png_path.replace(os.path.sep, "/"))
            
        # and finally render!
        try:
            # pick mid frame
            current_in = nuke.root()["first_frame"].value()
            current_out = nuke.root()["last_frame"].value()
            frame_to_render = (current_out - current_in) / 2 + current_in
            frame_to_render = int(frame_to_render)
            render_node_name = "%s.create_thumbnail" % node.name()
            # and do it - always render the first view we find.
            first_view = nuke.views()[0]
            nuke.execute(render_node_name, 
                         start=frame_to_render, 
                         end=frame_to_render, 
                         incr=1, 
                         views=[first_view])
        except Exception, e:
            self._app.engine.log_warning("Thumbnail could not be generated: %s" % e)
            # remove the temp file
            try:
                os.remove(png_path)
            except:
                pass
            png_path = None
        finally:
            # reset paths
            th_node.knob("file").setValue("")
            th_node.knob("proxy").setValue("")
            th_node.knob('disable').setValue(True)
    
        return png_path
        
    def show_in_fs(self, node):
        """
        Shows the location of the node in the file system.
        This is a callback which is executed when the show in fs
        button is pressed on the nuke write node.
        """
        
        files = self.get_files_on_disk(node)
        if len(files) == 0:
            nuke.message("There are no renders for this node yet!\n"
                         "When you render, the files will be written to "
                         "the following location:\n\n%s" % self.compute_path(node))
        else:
            
            render_dir = os.path.dirname(files[0])

            system = platform.system()
            
            # run the app
            if system == "Linux":
                cmd = 'xdg-open "%s"' % render_dir
            elif system == "Darwin":
                cmd = "open '%s'" % render_dir
            elif system == "Windows":
                cmd = 'cmd.exe /C start "Folder" "%s"' % render_dir
            else:
                raise Exception("Platform '%s' is not supported." % system)
            
            self._app.engine.log_debug("Executing command '%s'" % cmd)
            exit_code = os.system(cmd)
            if exit_code != 0:
                self.log_error("Failed to launch '%s'!" % cmd)
            
    def get_files_on_disk(self, node):
        """
        Returns the files on disk associated with this node
        """
        file_name = self.compute_path(node)
        template = self.get_render_template(node)
        
        if not template.validate(file_name):
            raise Exception("Could not resolve the files on disk for node %s."
                            "The path '%s' is not recognized by Tank!" % (node.name(), file_name))
        
        fields = template.get_fields(file_name)
        # make sure we don't look for any eye - %V or SEQ - %04d stuff
        frames = self._app.engine.tank.find_files(template, fields, ["SEQ", "eye"])   
        
        return frames
    
    def exists_on_disk(self, node):
        """
        returns true if this node has been rendered to disk
        """
        return (len(self.get_files_on_disk(node)) > 0)
    
    def get_channel_from_node(self, node):
        """
        returns the channel for a tank write node
        """
        channel_knob = node.knob("tank_channel")
        return channel_knob.value()
            
    def get_nodes(self):
        """
        Returns a list of tank write nodes
        """
        return nuke.allNodes("WriteTank")
        
    def on_before_render(self, node):
        """
        callback from nuke whenever a tank write node is about to be rendered.
        note that the node parameter represents the write node inside of the gizmo.
        """        
        # check if proxy render or not
        if nuke.root()['proxy'].value():
            # proxy mode
            out_file = node.knob("proxy").evaluate()
        else:
            out_file = node.knob("file").evaluate()
        
        out_dir = os.path.dirname(out_file)
        
        # create folders!
        self._app.engine.create_folder(out_dir)
        
    def on_after_render(self, node):
        """
        callback from nuke whenever a tank write node has finished rendering.
        note that the node parameter represents the write node inside of the gizmo.
        """
        pass
    
    def on_before_frame(self, node):
        """
        callback from nuke whenever a tank write node is about to render a frame.
        note that the node parameter represents the write node inside of the gizmo.
        """
        pass
    
    def on_after_frame(self, node):
        """
        callback from nuke whenever a tank write node is has finished rendering a frame.
        note that the node parameter represents the write node inside of the gizmo.
        """
        pass
    
    
  
