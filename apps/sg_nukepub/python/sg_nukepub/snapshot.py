"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

"""
import nukescripts
import nuke
import os
import shutil
import datetime

from tank import TankError

# modes for snapshot operation
(SNAPSHOT_NEW, SNAPSHOT_VERSION_UP) = range(2)


class TankSnapshotHandler(object):
    
    def __init__(self, app):
        self._app = app
        self._work_template = self._app.get_template("template_work")
        self._snapshot_template = self._app.get_template("template_snapshot")

    def _get_existing_version_numbers(self, path):
        """
        Returns the version numbers that currently exist on disk for a file
        """
        # get all versions 
        versions = self._app.engine.tank.find_files(self._work_template, 
                                                    self._work_template.get_fields(path), 
                                                    ["version"])
        version_numbers = [ self._work_template.get_fields(x).get("version") for x in versions ]
        
        return version_numbers


    def _do_actual_snapshot(self, path, mode):
        """
        Does the actual snapshot.
        The path is a "real" path, not one of those nuke paths with 
        / as the separator regarless of OS.
        
        returns False on failure, true on success.
        """
        
        # ensure that it is reasonable
        if not self._work_template.validate(path):
            nuke.message("Invalid snapshot path!")
            return
        
        # get all versions 
        version_numbers = self._get_existing_version_numbers(path)       
        # get our version
        curr_version_number = self._work_template.get_fields(path).get("version")
            
        
        if mode == SNAPSHOT_NEW:
            # ensure that no versions or snapshots exist with this version
            if len(version_numbers) > 0:
                nuke.message("A snapshot with that name already exists! Please choose another name.")
                return
            else:
                new_version_number = 1
            
        elif mode == SNAPSHOT_VERSION_UP:
            
            # ensure that we are the highest number
            if max(version_numbers) > curr_version_number:
                # there is a higher version number - this means that someone is working 
                # on an old version of the file.
                new_version_number = max(version_numbers) + 1
            else:
                # all okay, this is the highest version!
                new_version_number = curr_version_number + 1
            
        else:
            nuke.message("unknown mode!")
            return
        
        # calc new path
        fields = self._work_template.get_fields(path)
        fields["version"] = new_version_number
        new_path = self._work_template.apply_fields(fields)
                    
        nuke.scriptSaveAs(new_path)
    
        return True
            
    def validate_publish_snapshot(self, path):
        """
        Validate the snapshot in conjunction with a publish
        """
        
        # get all versions 
        version_numbers = self._get_existing_version_numbers(path)       
        # get our version
        curr_version_number = self._work_template.get_fields(path).get("version")
        
        # ensure that we are the highest number
        if max(version_numbers) > curr_version_number:
            new_version_number = max(version_numbers) + 1
            msg =  "Your current work file is v%03d, however a more recent " % curr_version_number
            msg += "version (v%03d) already exists. After snapshotting, your version " % max(version_numbers)
            msg += "will become v%03d, thereby shadowing some previous work. " % new_version_number
            msg += "Are you sure you want to proceed?"
    
            if not nuke.ask(msg):
                # exit
                return False
        
        return True
        
        
    def publish_snapshot(self, path):
        """
        Version up the snapshot file in conjunction with a publish
        """
        self._do_actual_snapshot(path, SNAPSHOT_VERSION_UP)    
    
    def manual_version_up(self):
        """
        Shows a UI where the user can do a manual version up.
        Then saves the work file with the new version number.
        """
        
        # first make sure it is actually a proper tank snapsho
        
        # on Windows, Nuke returns forward-slashes instead of backslashes
        # while we expect backslashes
        curr_filename = nuke.root().name().replace("/", os.path.sep)
        
        if not self._work_template.validate(curr_filename):
            
            # not a work file!
            nuke.message("The current file is not a Tank work file. "
                         "Please do a Snapshot As in order to create a work file.")
            self.snapshot_as()
            return

        # all good, it is a tank work file - ask for new version no
        f = self._work_template.get_fields(curr_filename)
        curr_version = f["version"]

        # defer import to ensure that command line mode in nuke works
        from snapshot_ui import VersionUpPanel
        d = VersionUpPanel(curr_version)
        result = d.showModalDialog()
        if result:
            f["version"] = d.get_new_version()
            new_filename = self._work_template.apply_fields(f)
            if os.path.exists(new_filename):
                nuke.message("A file with version number %d already exists. " 
                             "Please choose another number.")
            else:
                nuke.scriptSaveAs(new_filename)
    
    def snapshot_as(self):
        """
        Shows a dialog which lets a user specify file name, branch etc. 
        """
        
        # defer import to ensure that command line mode in nuke works
        from snapshot_ui import SnapshotAsPanel
        d = SnapshotAsPanel(self._app)
        result = d.showModalDialog()
        if result:
            # user clicked ok
            path = d.get_path()
            # do the actual snapshot
            try:
                self._do_actual_snapshot(path, SNAPSHOT_NEW)
            except:
                self._app.engine.log_exception("Could not snapshot as!")
    
    def snapshot(self):
        """
        Does a silent snapshot if file has already been snapshotted.
        Shows the snapshot UI if the file is brand new.
        """ 
        
        if nuke.root().name() == "Root":
            # we have not yet done a save as - present UI dialog
            self.snapshot_as()
        
        else:
            # on Windows, Nuke returns forward-slashes instead of backslashes
            # while we expect backslashes
            curr_filename = nuke.root().name().replace("/", os.path.sep)
            
            # first make sure that our current file actually matches the tank
            # work template. otherwise we do a snapshot-as + a message
            if not self._work_template.validate(curr_filename):
                
                # not a work file!
                nuke.message("The current file is not a Tank work file. "
                             "Please do a Snapshot As in order to create a work file.")
                self.snapshot_as()
                
            else:
                # file looks ok, proceed w snapshot
                nuke.scriptSave()
                fields = self._work_template.get_fields(curr_filename)
                fields["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                snapshot_path = self._snapshot_template.apply_fields(fields)  
                
                # make sure the folder exists
                # todo: push this IO into a hook
                snap_folder = os.path.dirname(snapshot_path)
                if not os.path.exists(snap_folder):
                    self._app.engine.log_debug("Snapshot: creating folder %s" % snap_folder)
                    os.makedirs(snap_folder, 0777)
                
                # todo: push this IO into a hook
                self._app.engine.log_debug("Snapshot: Copying %s --> %s" % (curr_filename, snapshot_path))                
                shutil.copy2(curr_filename, snapshot_path)
                
            
            
        
